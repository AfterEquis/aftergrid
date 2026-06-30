#!/usr/bin/env python3
import asyncio
import base64
import json
import os
import sys
import uuid
import argparse
import subprocess
from datetime import datetime
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import websockets
import logging
# Silenciamos los logs de websockets para evitar tracebacks ruidosos en stderr si se accede por navegador
logging.getLogger('websockets').setLevel(logging.CRITICAL)
from prompt_toolkit.application import Application
from prompt_toolkit.layout.containers import HSplit, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.application.current import get_app
from prompt_toolkit.lexers import Lexer
from prompt_toolkit.formatted_text.ansi import ANSI
from rich.console import Console

# Sal estática para derivar la clave criptográfica idéntica en ambos lados
SALT = b"offgrid-secure-terminal-chat-salt-2026"

def derive_key(password: str) -> bytes:
    """Deriva una clave Fernet (AES-128-CBC + HMAC) a partir de una contraseña."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT,
        iterations=100000,
    )
    return base64.urlsafe_b64encode(kdf.derive(password.encode()))

class EncryptedChat:
    def __init__(self, key: bytes, nickname: str):
        self.fernet = Fernet(key)
        self.nickname = nickname
        # Historial de mensajes locales enviados por mí para control de Acks
        # msg_id -> {text, timestamp, status}  (status: sent, delivered, read)
        self.my_messages = {}
        # Historial de mensajes recibidos (lista de strings formateados ANSI)
        self.message_history = []
        self.app = None
        self.chat_area = None
        self.input_field = None
        self.websocket = None
        self.is_connected = False
        self.peer_nickname = "Otro"
        self.tunnel_process = None
        self.tunnel_url = None

    def encrypt(self, data: dict) -> str:
        """Cifra un diccionario JSON y devuelve una cadena Base64."""
        json_str = json.dumps(data)
        encrypted_bytes = self.fernet.encrypt(json_str.encode())
        return encrypted_bytes.decode()

    def decrypt(self, encrypted_str: str) -> dict:
        """Descifra una cadena Base64 a un diccionario JSON."""
        decrypted_bytes = self.fernet.decrypt(encrypted_str.encode())
        return json.loads(decrypted_bytes.decode())

    def format_time(self, dt=None):
        if not dt:
            dt = datetime.now()
        return dt.strftime("%H:%M:%S")

    def update_ui(self):
        """Redibuja el área de chat reconstruyendo el historial con los estados actualizados."""
        if not self.chat_area or not self.app:
            return
        
        lines = []
        # Título superior
        status_color = "32" if self.is_connected else "31" # 32=verde, 31=rojo
        lines.append(f"\033[1;36m┌─── AfterGrid Chat Cifrado ─────────────────────────────────────────────────┐\033[0m")
        lines.append(f"\033[1;36m│\033[0m Nick: \033[1;33m{self.nickname}\033[0m | Conectado con: \033[1;35m{self.peer_nickname}\033[0m | Estado: \033[1;{status_color}m{'● Conectado' if self.is_connected else '○ Desconectado'}\033[0m")
        if self.tunnel_url:
            lines.append(f"\033[1;36m│\033[0m Túnel de Internet activo: \033[1;32m{self.tunnel_url}\033[0m")
        lines.append(f"\033[1;36m└────────────────────────────────────────────────────────────────────────────┘\033[0m")
        lines.append("")

        # Mensajes
        for item in self.message_history:
            lines.append(item)

        self.chat_area.text = "\n".join(lines)
        # Scroll automático al final
        self.chat_area.buffer.cursor_position = len(self.chat_area.text)
        self.app.invalidate()

    def add_system_message(self, text: str, is_error: bool = False):
        """Agrega un mensaje de sistema al historial (Amarillo para info, Rojo brillante para errores)."""
        time_str = self.format_time()
        color = "\033[1;31m" if is_error else "\033[1;33m"
        self.message_history.append(f"{color}[{time_str}] [Sistema] {text}\033[0m")
        self.update_ui()

    def add_incoming_message(self, sender: str, text: str, time_str: str):
        """Agrega un mensaje recibido del otro usuario."""
        self.message_history.append(f"\033[1;35m[{time_str}] {sender}:\033[0m {text}")
        self.update_ui()

    def add_outgoing_message(self, text: str, msg_id: str, time_str: str):
        """Agrega un mensaje enviado por mí, con marcas de estado dinámicas."""
        self.my_messages[msg_id] = {
            "text": text,
            "time": time_str,
            "status": "sent" # sent -> delivered -> read
        }
        self.render_my_messages_in_history(msg_id)
        self.update_ui()

    def render_my_messages_in_history(self, msg_id):
        """Genera el formateo visual para uno de mis mensajes y lo añade al historial."""
        msg = self.my_messages[msg_id]
        status_indicator = "\033[30m✓\033[0m" # Un check gris (enviado)
        if msg["status"] == "delivered":
            status_indicator = "\033[1;30m✓✓\033[0m" # Doble check gris oscuro (entregado)
        elif msg["status"] == "read":
            status_indicator = "\033[1;34m✓✓\033[0m" # Doble check azul (leído)

        # Buscamos si ya existe el mensaje en la pantalla para actualizarlo, si no, lo agregamos
        search_key = f"ID:{msg_id}"
        formatted_line = f"\033[1;32m[{msg['time']}] Tú:\033[0m {msg['text']}  {status_indicator} \033[30m{search_key}\033[0m"
        
        # Intentamos actualizar la línea existente
        for i, line in enumerate(self.message_history):
            if search_key in line:
                self.message_history[i] = formatted_line
                return
        
        # Si no existe, lo agregamos
        self.message_history.append(formatted_line)

    def handle_ack(self, msg_id: str, ack_type: str):
        """Actualiza el estado de confirmación de un mensaje enviado."""
        if msg_id in self.my_messages:
            current_status = self.my_messages[msg_id]["status"]
            # Evitamos sobreescribir 'read' con 'delivered'
            if ack_type == "read":
                self.my_messages[msg_id]["status"] = "read"
            elif ack_type == "delivered" and current_status == "sent":
                self.my_messages[msg_id]["status"] = "delivered"
            
            self.render_my_messages_in_history(msg_id)
            self.update_ui()

    async def send_message(self, text: str):
        """Envía un mensaje de texto cifrado a través del socket."""
        if not self.is_connected or not self.websocket:
            self.add_system_message("Error: No hay conexión con el otro terminal. Tu compañero debe conectarse a tu URL primero.", is_error=True)
            return

        msg_id = str(uuid.uuid4())[:8]
        time_str = self.format_time()
        
        # Agregar localmente
        self.add_outgoing_message(text, msg_id, time_str)

        # Cifrar payload
        payload = {
            "type": "msg",
            "id": msg_id,
            "sender": self.nickname,
            "content": text,
            "time": time_str
        }
        encrypted_payload = self.encrypt(payload)
        
        try:
            await self.websocket.send(encrypted_payload)
        except Exception as e:
            self.add_system_message(f"Error al enviar mensaje: {e}", is_error=True)
            self.is_connected = False
            self.update_ui()

    async def send_ack(self, msg_id: str, ack_type: str):
        """Envía una confirmación de entrega (delivered) o lectura (read) cifrada."""
        if not self.websocket:
            return
        payload = {
            "type": ack_type,
            "msg_id": msg_id,
            "sender": self.nickname
        }
        encrypted_payload = self.encrypt(payload)
        try:
            await self.websocket.send(encrypted_payload)
        except Exception:
            pass

    async def handle_incoming_payload(self, encrypted_data: str):
        """Descifra y procesa un paquete JSON entrante."""
        try:
            payload = self.decrypt(encrypted_data)
            p_type = payload.get("type")
            sender = payload.get("sender", "Otro")
            self.peer_nickname = sender

            if not self.is_connected:
                self.is_connected = True
                self.update_ui()

            if p_type == "msg":
                msg_id = payload.get("id")
                content = payload.get("content")
                time_str = payload.get("time")
                
                # Mostrar en pantalla
                self.add_incoming_message(sender, content, time_str)
                
                # Enviar confirmación de entrega (delivered) inmediatamente
                await self.send_ack(msg_id, "delivered")
                
                # Enviar confirmación de lectura (read) inmediatamente (ya que se muestra en pantalla)
                await self.send_ack(msg_id, "read")

            elif p_type == "delivered":
                msg_id = payload.get("msg_id")
                self.handle_ack(msg_id, "delivered")

            elif p_type == "read":
                msg_id = payload.get("msg_id")
                self.handle_ack(msg_id, "read")

            elif p_type == "ping":
                # Responder pong para mantener viva la conexión
                pong = self.encrypt({"type": "pong", "sender": self.nickname})
                await self.websocket.send(pong)
                
            elif p_type == "pong":
                pass

        except Exception as e:
            # Si no se puede descifrar o procesar, se ignora (posible clave incorrecta de un intruso)
            pass

    async def connection_handler(self, ws):
        """Maneja la conexión WebSocket activa (servidor o cliente)."""
        self.websocket = ws
        self.is_connected = True
        self.add_system_message("¡Conexión establecida con el otro terminal! Cifrado activo.")
        
        # Intercambiar pings iniciales para sincronizar nicks
        try:
            init_ping = self.encrypt({"type": "ping", "sender": self.nickname})
            await ws.send(init_ping)
            
            async for message in ws:
                await self.handle_incoming_payload(message)
        except websockets.exceptions.ConnectionClosed:
            self.add_system_message("La conexión se ha cerrado.")
        except Exception as e:
            self.add_system_message(f"Error en la conexión: {e}", is_error=True)
        finally:
            self.is_connected = False
            self.websocket = None
            self.update_ui()

    async def start_server(self, host: str, port: int):
        """Inicia el servidor WebSocket local."""
        self.add_system_message(f"Iniciando servidor local en ws://{host}:{port} ...")
        try:
            async def handler(ws):
                await self.connection_handler(ws)

            server = await websockets.serve(handler, host, port)
            self.add_system_message(f"Servidor escuchando en puerto {port}. Esperando conexión remota...")
            return server
        except Exception as e:
            self.add_system_message(f"Error al iniciar servidor: {e}", is_error=True)
            return None

    async def start_client(self, url: str):
        """Inicia el bucle de reconexión del cliente WebSocket."""
        self.add_system_message(f"Conectando a {url} ...")
        while True:
            try:
                # Si la URL viene de Serveo como https://, la transformamos en wss://
                ws_url = url.replace("https://", "wss://").replace("http://", "ws://")
                async with websockets.connect(ws_url, ping_interval=20, ping_timeout=20) as ws:
                    await self.connection_handler(ws)
            except Exception as e:
                # Reintentar cada 5 segundos
                await asyncio.sleep(5)

    def run_serveo_tunnel(self, local_port: int):
        """Inicia el túnel de Serveo por SSH en un hilo secundario y extrae la URL."""
        self.add_system_message("Iniciando túnel seguro a través de Serveo...")
        
        # Lanzamos el comando SSH redirigiendo HTTP al puerto local del WebSocket
        cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-R", f"80:localhost:{local_port}", "serveo.net"]
        try:
            # Arrancamos el túnel. serveo.net imprimirá la URL pública en stdout
            self.tunnel_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1
            )
            
            # Buscamos la URL de redirección en las primeras líneas de salida
            for _ in range(15):
                line = self.tunnel_process.stdout.readline()
                if not line:
                    break
                if "Forwarding HTTP traffic from" in line:
                    # Extraer la URL
                    parts = line.split("from")
                    if len(parts) > 1:
                        self.tunnel_url = parts[1].strip()
                        self.add_system_message(f"¡Túnel SSH activo!")
                        self.add_system_message(f"Comparte esta URL con la otra persona en Modo Cliente:")
                        self.add_system_message(f"  {self.tunnel_url}")
                        self.add_system_message(f"  (NOTA: No la abras en tu navegador, es solo para el cliente de consola).")
                        self.update_ui()
                        break
            
            # Bucle de fondo para evitar que se llene el buffer de stdout
            def discard_output():
                try:
                    for _ in self.tunnel_process.stdout:
                        pass
                except Exception:
                    pass
            
            import threading
            threading.Thread(target=discard_output, daemon=True).start()

        except Exception as e:
            self.add_system_message(f"Error al iniciar túnel SSH: {e}", is_error=True)

    def close_tunnel(self):
        if self.tunnel_process:
            self.tunnel_process.terminate()
            self.tunnel_process = None
            self.tunnel_url = None
            self.add_system_message("Túnel SSH cerrado.")

class AnsiLexer(Lexer):
    """Lexer personalizado para prompt-toolkit que interpreta secuencias de escape ANSI."""
    def lex_document(self, document):
        def get_line(line_number):
            line_text = document.lines[line_number]
            return ANSI(line_text).__pt_formatted_text__()
        return get_line

def build_tui(chat_client: EncryptedChat):
    """Construye la interfaz de usuario en terminal usando prompt-toolkit."""
    # Área de historial del chat (solo lectura, con scroll y soporte ANSI)
    chat_client.chat_area = TextArea(
        read_only=True,
        scrollbar=True,
        focusable=False,
        lexer=AnsiLexer(),
        text="Inicializando chat...\n"
    )

    # Campo de entrada de mensajes (con prompt ANSI coloreado)
    chat_client.input_field = TextArea(
        multiline=False,
        height=1,
        prompt=ANSI("\033[1;32mEscribe un mensaje > \033[0m")
    )

    # Atajos de teclado (Enter para enviar)
    kb = KeyBindings()

    @kb.add('enter')
    def handle_enter(event):
        text = chat_client.input_field.text.strip()
        if text:
            # Si no hay conexión, mostrar error y NO borrar el mensaje escrito
            if not chat_client.is_connected or not chat_client.websocket:
                chat_client.add_system_message("Error: No hay conexión con el otro terminal. Tu compañero debe conectarse a tu URL primero.", is_error=True)
                return
                
            # Si hay conexión, limpiar campo de texto y enviar
            chat_client.input_field.text = ""
            asyncio.create_task(chat_client.send_message(text))

    @kb.add('c-c')
    def handle_exit(event):
        """Salir de la aplicación con Ctrl+C."""
        chat_client.close_tunnel()
        event.app.exit()

    # Layout de la interfaz (Historial arriba, línea separadora con estilo, entrada abajo)
    layout = Layout(
        HSplit([
            chat_client.chat_area,
            Window(height=1, char='─', style='class:divider'), # Línea divisora con estilo
            chat_client.input_field
        ]),
        focused_element=chat_client.input_field # Foco inicial en el input de texto
    )

    # Estilos visuales
    style = Style.from_dict({
        '': '#ffffff',
        'scrollbar.button': '#333333',
        'scrollbar.background': '#111111',
        'divider': '#00ffff', # Color cyan para la línea divisora
    })

    # Crear la aplicación prompt-toolkit
    app = Application(
        layout=layout,
        key_bindings=kb,
        style=style,
        full_screen=True
    )
    
    chat_client.app = app
    return app

def get_local_ip():
    """Obtiene la IP local de la interfaz Wi-Fi/LAN activa."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No necesita conectarse realmente para obtener la IP
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip

async def main():
    parser = argparse.ArgumentParser(description="AfterGrid: Chat de Terminal Cifrado E2EE y P2P")
    parser.add_argument("--serve", action="store_true", help="Actuar como servidor")
    parser.add_argument("--connect", type=str, help="URL o IP del servidor a conectar")
    parser.add_argument("--port", type=int, default=5000, help="Puerto del servidor (por defecto 5000)")
    parser.add_argument("--internet", action="store_true", help="Exponer el servidor a internet mediante Serveo (solo en modo --serve)")
    args = parser.parse_args()

    # Si no se proporcionan argumentos, preguntar de forma interactiva
    serve_mode = args.serve
    connect_url = args.connect
    port = args.port
    internet_tunnel = args.internet

    console = Console()
    console.print("[bold cyan]======================================================[/bold cyan]")
    console.print("[bold cyan]       AfterGrid - Chat de Terminal Cifrado E2EE     [/bold cyan]")
    console.print("[bold cyan]======================================================[/bold cyan]\n")

    if not serve_mode and not connect_url:
        console.print("[yellow]Selecciona el modo de funcionamiento:[/yellow]")
        console.print("  [1] Servidor (Esperar conexión)")
        console.print("  [2] Cliente (Conectarse a otro terminal)")
        choice = input("\nElige una opción (1 o 2): ").strip()
        
        if choice == "1":
            serve_mode = True
            net_choice = input("¿Quieres chatear a través de [1] Wi-Fi Local/LAN o [2] Internet (túnel seguro)? [1/2]: ").strip()
            if net_choice == "2":
                internet_tunnel = True
        elif choice == "2":
            connect_url = input("\nIntroduce la dirección de conexión (ej: ws://192.168.1.50:5000 o la URL de internet): ").strip()
            if not connect_url:
                console.print("[red]Error: Debes proporcionar una dirección válida.[/red]")
                return
        else:
            console.print("[red]Opción no válida.[/red]")
            return

    # Solicitar datos de seguridad y perfil
    import getpass
    console.print("\n[bold green]► Seguridad[/bold green]")
    password = getpass.getpass("Introduce la frase de contraseña compartida (debe ser la misma para ambos): ")
    if not password:
        console.print("[red]Error: La contraseña no puede estar vacía.[/red]")
        return

    nickname = input("\nIntroduce tu apodo (Nickname): ").strip()
    if not nickname:
        nickname = "Usuario1" if serve_mode else "Usuario2"

    # Inicializar cliente
    key = derive_key(password)
    chat_client = EncryptedChat(key, nickname)

    # Construir la interfaz de terminal (TUI)
    app = build_tui(chat_client)

    # Lanzar tareas de red en segundo plano
    if serve_mode:
        # Modo Servidor
        server_task = await chat_client.start_server("0.0.0.0", port)
        chat_client.add_system_message("Modo Servidor iniciado.")
        
        if internet_tunnel:
            # Lanzamos Serveo SSH en background
            chat_client.run_serveo_tunnel(port)
        else:
            # Mostrar IP local para conexión directa en LAN
            local_ip = get_local_ip()
            chat_client.add_system_message(f"Comparte tu IP local con la otra persona:")
            chat_client.add_system_message(f"  ws://{local_ip}:{port}")
            chat_client.update_ui()
    else:
        # Modo Cliente
        asyncio.create_task(chat_client.start_client(connect_url))
        chat_client.add_system_message("Modo Cliente iniciado. Intentando conectar...")

    # Ejecutar la TUI de prompt-toolkit (bloquea hasta que la aplicación sale con Ctrl+C)
    try:
        await app.run_async()
    finally:
        # Asegurarse de cerrar el túnel al salir
        chat_client.close_tunnel()
        console.print("\n[bold yellow]Chat AfterGrid cerrado. ¡Hasta luego![/bold yellow]\n")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
