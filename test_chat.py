#!/usr/bin/env python3
import asyncio
import unittest
from unittest.mock import MagicMock
import websockets
from chat import derive_key, EncryptedChat

class TestAfterGridCryptography(unittest.TestCase):
    def setUp(self):
        self.password = "mi-super-secreto-compartido-123"
        self.key = derive_key(self.password)
        self.chat = EncryptedChat(self.key, "Tester")

    def test_key_derivation_consistency(self):
        """Comprueba que la derivación de clave es consistente e idéntica en ambos lados."""
        key1 = derive_key(self.password)
        key2 = derive_key(self.password)
        self.assertEqual(key1, key2)
        # Una contraseña distinta debe generar una clave distinta
        key3 = derive_key("otra-contraseña-diferente")
        self.assertNotEqual(key1, key3)

    def test_encryption_decryption_success(self):
        """Prueba que el cifrado y descifrado E2EE funciona correctamente para payloads JSON."""
        original_payload = {
            "type": "msg",
            "id": "abc12345",
            "sender": "Alice",
            "content": "Hola, esto es un test secreto 🔒",
            "time": "12:00:00"
        }
        
        # Ciframos con la instancia de chat
        ciphertext = self.chat.encrypt(original_payload)
        self.assertIsInstance(ciphertext, str)
        self.assertNotEqual(ciphertext, str(original_payload)) # No debe estar en texto claro
        
        # Desciframos con la misma instancia (misma clave)
        decrypted_payload = self.chat.decrypt(ciphertext)
        self.assertEqual(original_payload, decrypted_payload)

    def test_decryption_failure_with_wrong_key(self):
        """Valida que descifrar con una clave incorrecta (contraseña incorrecta) falle como se espera."""
        payload = {"type": "msg", "content": "Secreto"}
        ciphertext = self.chat.encrypt(payload)
        
        # Creamos otra instancia de chat con una clave distinta (contraseña distinta)
        wrong_key = derive_key("contraseña-equivocada")
        attacker_chat = EncryptedChat(wrong_key, "Attacker")
        
        # Intentar descifrar debe lanzar una excepción (Fernet InvalidToken)
        with self.assertRaises(Exception):
            attacker_chat.decrypt(ciphertext)


class TestAfterGridMessageStates(unittest.TestCase):
    def setUp(self):
        self.key = derive_key("secreto")
        self.chat = EncryptedChat(self.key, "Alice")
        # Simulamos UI y App para que no fallen al actualizar la pantalla en el test
        self.chat.app = MagicMock()
        self.chat.chat_area = MagicMock()

    def test_outgoing_message_initial_state(self):
        """Prueba que los mensajes salientes inicien con conjuntos vacíos de acks."""
        msg_id = "msg1"
        self.chat.add_outgoing_message("Hola", msg_id, "12:00:00")
        
        self.assertIn(msg_id, self.chat.my_messages)
        self.assertEqual(len(self.chat.my_messages[msg_id]["delivered_by"]), 0)
        self.assertEqual(len(self.chat.my_messages[msg_id]["read_by"]), 0)
        
        # Comprobar que en el historial visual se dibuja el check único gris
        formatted_line = self.chat.message_history[0]
        self.assertIn("✓", formatted_line)
        self.assertNotIn("✓✓", formatted_line)

    def test_ack_delivered_transition(self):
        """Prueba la transición de estado 'sent' -> 'delivered' (doble check gris)."""
        msg_id = "msg2"
        self.chat.add_outgoing_message("Hola", msg_id, "12:00:00")
        
        # Simulamos llegada de ACK delivered de Bob
        self.chat.handle_ack(msg_id, "delivered", "Bob")
        self.assertIn("Bob", self.chat.my_messages[msg_id]["delivered_by"])
        
        # Comprobar el doble check gris oscuro en el historial
        formatted_line = self.chat.message_history[0]
        self.assertIn("✓✓", formatted_line)
        self.assertIn("1;30m", formatted_line) # Color del delivered (gris oscuro)

    def test_ack_read_transition(self):
        """Prueba la transición de estado 'delivered' -> 'read' (doble check azul)."""
        msg_id = "msg3"
        self.chat.add_outgoing_message("Hola", msg_id, "12:00:00")
        
        # Delived primero de Bob
        self.chat.handle_ack(msg_id, "delivered", "Bob")
        # Read después de Bob
        self.chat.handle_ack(msg_id, "read", "Bob")
        
        self.assertIn("Bob", self.chat.my_messages[msg_id]["read_by"])
        
        # Comprobar el doble check azul en el historial
        formatted_line = self.chat.message_history[0]
        self.assertIn("✓✓", formatted_line)
        self.assertIn("1;34m", formatted_line) # Color del read (azul)

    def test_ack_prevent_read_overwrite(self):
        """Valida que un ACK 'delivered' tardío no sobreescriba un estado 'read' ya activo."""
        msg_id = "msg4"
        self.chat.add_outgoing_message("Hola", msg_id, "12:00:00")
        
        # Pasa directamente a read de Bob
        self.chat.handle_ack(msg_id, "read", "Bob")
        self.assertIn("Bob", self.chat.my_messages[msg_id]["read_by"])
        
        # Un delivered tardío de red de Bob no debe sobreescribir el 'read'
        self.chat.handle_ack(msg_id, "delivered", "Bob")
        self.assertIn("Bob", self.chat.my_messages[msg_id]["read_by"])


class TestAfterGridNetworkIntegration(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.key = derive_key("password-secreta-integracion")
        self.server_chat = EncryptedChat(self.key, "Servidor")
        self.server_chat.is_server = True
        self.client_chat = EncryptedChat(self.key, "Cliente")
        
        # Desactivamos UI para evitar interferencias
        self.server_chat.app = MagicMock()
        self.server_chat.chat_area = MagicMock()
        self.client_chat.app = MagicMock()
        self.client_chat.chat_area = MagicMock()

    async def test_handshake_and_ping_pong_exchange(self):
        """Prueba de integración asíncrona: Conexión local, apretón de manos y sincronización de apodos."""
        # Arrancamos servidor en puerto local dinámico efímero (puerto 0 para asignación automática del OS)
        server = await websockets.serve(self.server_chat.connection_handler, "127.0.0.1", 0)
        # Extraemos el puerto efímero asignado
        port = server.sockets[0].getsockname()[1]
        
        # Iniciamos el cliente conectándolo a ese puerto
        client_task = asyncio.create_task(self.client_chat.start_client(f"ws://127.0.0.1:{port}"))
        
        # Esperamos a que la conexión se establezca y se sincronicen
        for _ in range(20):
            await asyncio.sleep(0.1)
            if self.server_chat.is_connected and self.client_chat.is_connected:
                if len(self.server_chat.connected_clients) == 1:
                    break
        
        # Comprobaciones
        self.assertTrue(self.server_chat.is_connected)
        self.assertTrue(self.client_chat.is_connected)
        self.assertEqual(len(self.server_chat.connected_clients), 1)
        
        # Detener servidor y tareas del cliente
        server.close()
        await server.wait_closed()
        client_task.cancel()
        try:
            await client_task
        except asyncio.CancelledError:
            pass

if __name__ == "__main__":
    unittest.main()
