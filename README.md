# AfterGrid ── Chat de Terminal Cifrado y Grupal (P2P / Salas)

**AfterGrid** es un chat interactivo para tu terminal diseñado para funcionar tanto en redes locales (completamente offline/sin internet) como a través de internet (detrás de firewalls/NATs y sin necesidad de configurar tu router). 

A diferencia de los chats directos comunes, **AfterGrid** soporta salas con **múltiples participantes simultáneos** (chat grupal). Toda la comunicación está protegida por **Cifrado de Extremo a Extremo (E2EE)** mediante criptografía simétrica fuerte (AES-128-CBC + HMAC-SHA256) derivada de una frase de contraseña compartida usando PBKDF2.

---

## 🚀 Características
*   **Soporte Multiusuario (Salas)**: El creador de la sala actúa como Hub y retransmite los mensajes y confirmaciones cifradas a todos los miembros de forma ciega.
*   **Cifrado E2EE Grupal**: La comunicación viaja en bloques cifrados incomprensibles. Solo quienes ingresen la misma contraseña al iniciar podrán descifrar la conversación.
*   **Confirmación de Vista Detallada**:
    *   `✓` (Gris claro) - Mensaje enviado por ti.
    *   `✓✓ (Alice)` (Gris oscuro) - Mensaje recibido físicamente por Alice.
    *   `✓✓ (Alice, Bob)` (Azul) - Mensaje visto en pantalla por Alice y Bob en tiempo real.
*   **UX Inteligente**:
    *   Foco de teclado automático en la caja de texto al iniciar.
    *   Retención de borrador: Si envías un mensaje sin nadie más en la sala, el programa te avisa en **rojo brillante** pero **no borra tu texto escrito** para que no lo pierdas.
*   **Silencio de Ruido de Red**: El servidor WebSockets tiene silenciado su logger para evitar que accesos web incidentales rompan la interfaz visual TUI con tracebacks de error.

---

## 🌐 ¿Qué significan las opciones de conexión?

Al iniciar el programa en modo Creador de Sala (`./run.sh`), el asistente te preguntará:  
*`¿Quieres chatear a través de [1] Wi-Fi Local/LAN o [2] Internet (túnel seguro)? [1/2]:`*

*   **1. Wi-Fi Local/LAN (Totalmente Offline)**: Los mensajes viajan directamente por ondas Wi-Fi entre las laptops. Ideal para descampados, montaña o zonas de catástrofe sin cobertura. Todos los participantes deben conectarse al mismo punto de acceso Wi-Fi (Hotspot/Zona Wi-Fi).
*   **2. Internet (Túnel Seguro)**: Los mensajes viajan globalmente por internet. El creador de la sala expone su puerto local temporalmente (vía SSH a `serveo.net`) para saltarse cortafuegos y CGNATs de los operadores sin abrir puertos en el router. Ambos necesitáis conexión a internet activa.

---

## 🛠️ Cómo Usarlo

Para comenzar, ejecuta el asistente interactivo:
```bash
./run.sh
```

### Opción A: Por Internet (Túnel Seguro)
1.  **Creador de la Sala (Servidor)**: Elige `Servidor (1)` > `Internet (2)` > Pon contraseña y apodo. Te dará una URL (ej. `https://xxx.serveousercontent.com`). Compártela con los invitados. *(No la abras en un navegador)*.
2.  **Participantes (Clientes)**: Elijan `Cliente (2)` > Peguen la URL del creador > Pongan **la misma contraseña** y sus apodos.

### Opción B: Fuera de la Red / Offline (Wi-Fi Local)
1.  **Preparación**: Conectad todos los ordenadores a la misma red Wi-Fi (incluso sin acceso a internet).
2.  **Creador de la Sala (Servidor)**: Elige `Servidor (1)` > `Wi-Fi Local (1)` > Pon contraseña y apodo. Te dará tu dirección de red local (ej. `ws://192.168.43.10:5000`).
3.  **Participantes (Clientes)**: Elijan `Cliente (2)` > Peguen la dirección del creador > Pongan **la misma contraseña** y sus apodos.

---

## 📡 Cómo lograr 400 Metros de Distancia (Offline)
El Wi-Fi de una laptop convencional tiene un rango de 50 a 100 metros en interiores. Para llegar a los **400 metros de distancia** de forma offline:
1.  **Línea de visión directa**: Buscad un terreno despejado sin edificios, colinas de tierra o arboledas densas en medio.
2.  **Antenas Wi-Fi USB de Largo Alcance**: Conectar una antena Wi-Fi USB de alta ganancia (direccional o Yagi) en las laptops extiende el rango de red a 1-2 kilómetros de forma económica.
3.  **Repetidor intermedio**: Podéis dejar un router Wi-Fi común a batería en medio del trayecto (a 200m de cada uno) para que todos se conecten a él.

---

## 🔒 Detalles Técnicos de Seguridad
1.  **Derivación**: Tu contraseña nunca viaja por la red. Se procesa localmente con `PBKDF2HMAC` y `SHA256` (100,000 iteraciones con sal estática) para derivar la clave simétrica.
2.  **Cifrado simétrico**: Los payloads viajan cifrados bajo el protocolo `Fernet` (AES-128 en modo CBC con firmas HMAC-SHA256).
3.  **Cifrado de Metadatos**: El paquete JSON (tipo, emisor, id, confirmaciones) se cifra al completo en un bloque único de caracteres base64 antes de ser transmitido. Un sniffer o el intermediario de red solo ven ruido indescifrable; no pueden saber quién escribe, cuándo o si es un mensaje o un acuse de recibo.

---

## 🧪 Pruebas Automatizadas
El repositorio incluye una suite completa de pruebas unitarias y de integración asíncrona. Puedes ejecutarlas para verificar el correcto funcionamiento de la criptografía y el protocolo de red:
```bash
python3 -m unittest test_chat.py
```
Las pruebas simulan un servidor y cliente reales en loopback (`localhost`), validan el apretón de manos inicial, cifrado/descifrado, resistencia ante claves atacantes erróneas y la transición correcta de los checks `✓` y `✓✓` en salas multiusuario.
