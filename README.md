# AfterGrid ── Chat de Terminal Cifrado y P2P

**AfterGrid** es un chat interactivo para tu terminal diseñado para funcionar tanto en redes locales (completamente offline/sin internet) como a través de internet (detrás de firewalls/NATs y sin necesidad de configurar tu router). 

Toda la comunicación está protegida por **Cifrado de Extremo a Extremo (E2EE)** mediante criptografía simétrica fuerte (AES-128-CBC + HMAC-SHA256) derivada de una frase de contraseña compartida usando PBKDF2.

---

## 🚀 Características
*   **Cifrado E2EE de Extremo a Extremo**: Ningún intermediario (ni tu router, ni el servidor de túneles) puede leer el contenido. Para la red, todo el tráfico son bytes de ruido incomprensibles.
*   **Confirmación de Entrega y Vista**:
    *   `✓` (Gris claro) - Mensaje enviado por tu terminal.
    *   `✓✓` (Gris oscuro) - Mensaje entregado físicamente en la otra terminal (Confirmación de entrega).
    *   `✓✓` (Azul/Celeste) - El destinatario ha visto el mensaje en su pantalla (Confirmación de lectura).
*   **UX Inteligente**:
    *   Foco de teclado automático en la caja de texto al iniciar.
    *   Retención de borrador: Si intentas enviar un mensaje estando desconectado, el programa te avisa en **rojo brillante** pero **no borra tu texto escrito** para que no pierdas tus mensajes largos.
*   **Silencio de Ruido de Red**: El servidor WebSockets tiene silenciado su logger de diagnóstico para evitar que los escaneos de puertos de internet o accesos por navegador web impriman tracebacks molestos en tu pantalla.

---

## 🌐 ¿Qué significan las opciones de conexión?

Al iniciar el programa en modo Servidor (`./run.sh`), el asistente te preguntará:  
*`¿Quieres chatear a través de [1] Wi-Fi Local/LAN o [2] Internet (túnel seguro)? [1/2]:`*

*   **1. Wi-Fi Local/LAN (Totalmente Offline)**: Los mensajes viajan por ondas Wi-Fi directamente de una laptop a otra. Úsalo si estás a corta distancia (hasta 400m en línea de visión), en el campo sin señal móvil o en situaciones sin red eléctrica/internet. Ambos debéis conectaros al mismo Wi-Fi (ej. un Hotspot creado por uno de los dos ordenadores).
*   **2. Internet (Túnel Seguro)**: Los mensajes viajan globalmente por internet. El script abre un "túnel de escape" seguro (vía SSH a `serveo.net`) para saltarse cortafuegos y NATs sin configurar el router. Úsalo si cada uno está en su casa o usa datos móviles de proveedores distintos. Ambos necesitáis internet.

---

## 🛠️ Cómo Usarlo

Para comenzar, ejecuta el asistente interactivo:
```bash
./run.sh
```

### Opción A: Por Internet (Túnel Seguro)
1.  **Servidor**: Elige `Servidor (1)` > `Internet (2)` > Pon contraseña y apodo. Te dará una URL (ej. `https://xxx.serveousercontent.com`). Compártela. *(No la abras en un navegador)*.
2.  **Cliente**: Elige `Cliente (2)` > Pega la URL > Pon **la misma contraseña** y apodo.

### Opción B: Fuera de la Red / Offline (Wi-Fi Local)
1.  **Preparación**: Conectad ambos ordenadores a la misma red Wi-Fi (incluso sin internet).
2.  **Servidor**: Elige `Servidor (1)` > `Wi-Fi Local (1)` > Pon contraseña y apodo. Te dará una IP local (ej. `ws://192.168.43.10:5000`).
3.  **Cliente**: Elige `Cliente (2)` > Pega la dirección IP > Pon **la misma contraseña** y apodo.

---

## 📡 Cómo lograr 400 Metros de Distancia (Offline)
El Wi-Fi convencional de una laptop tiene un rango de 50 a 100 metros en interiores debido a las paredes. Para llegar a los **400 metros de distancia** sin red móvil ni internet:
1.  **Línea de visión directa**: Evita obstáculos como edificios, árboles gruesos o lomas de tierra. En un descampado o una calle recta despejada, la señal Wi-Fi de una laptop puede alcanzar fácilmente más distancia.
2.  **Antenas Wi-Fi de Largo Alcance (USB)**: Puedes conectar una antena Wi-Fi USB de alta ganancia (con antena externa direccional o Yagi) en una o ambas laptops. Estas antenas son sumamente económicas y extienden el rango de Wi-Fi convencional a 1-2 kilómetros sin problemas.
3.  **Dispositivo repetidor intermedio**: Si podéis colocar un router Wi-Fi común alimentado por batería a mitad de camino (a 200m de cada uno), ambos os podréis conectar a él y hablar a través del modo local LAN de **AfterGrid**.

---

## 🔒 Detalles Técnicos de Seguridad
1.  **Derivación**: Tu contraseña en texto plano nunca se transmite. Se procesa localmente con `PBKDF2HMAC` usando `SHA256` y 100,000 iteraciones con un `SALT` estático para derivar la clave criptográfica.
2.  **Cifrado simétrico**: Los payloads viajan cifrados con el formato seguro de `Fernet` (AES-128 en modo CBC con firmas HMAC-SHA256).
3.  **Metadatos protegidos**: A diferencia de otros chats, no solo se cifra el texto del mensaje. Todo el paquete JSON (tipo de paquete, emisor, id, confirmaciones `delivered` y `read`) se cifra en un bloque único de ruido base64 antes de ser enviado. Ningún sniffer de red o el servidor de túneles SSH de Serveo puede discernir cuándo envías texto o cuándo estás recibiendo una confirmación de lectura.

---

## 🧪 Pruebas Automatizadas
El repositorio incluye una suite completa de pruebas unitarias y de integración asíncrona. Puedes ejecutarlas para verificar el correcto funcionamiento de la criptografía y el protocolo de red:
```bash
python3 -m unittest test_chat.py
```
Las pruebas simulan un servidor y cliente reales en loopback (`localhost`), validan el apretón de manos inicial, cifrado/descifrado, resistencia ante claves atacantes erróneas y la transición correcta de los checks `✓` y `✓✓`.
