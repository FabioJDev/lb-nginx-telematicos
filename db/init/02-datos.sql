-- db/init/02-datos.sql — datos de prueba deterministas (misma semilla en cada despliegue).
--   2000 productos en 8 categorías y 1000 usuarios: usuario1 … usuario1000, contraseña "clave123".

SELECT setseed(0.42);

INSERT INTO products (sku, name, category, price, stock, description)
SELECT
    'SKU-' || lpad(n::text, 5, '0'),
    (ARRAY['Cable','Adaptador','Router','Switch','Antena','Tarjeta','Servidor','Disco',
           'Memoria','Monitor','Teclado','Cámara','Sensor','Módem','Repetidor','Batería'])[1 + (n % 16)]
      || ' ' ||
    (ARRAY['Pro','Lite','Max','Plus','Mini','Ultra','Eco','Smart'])[1 + ((n / 16) % 8)]
      || ' ' || n,
    (ARRAY['redes','almacenamiento','periféricos','energía','seguridad','servidores','audio y video','accesorios'])[1 + (n % 8)],
    round((10 + random() * 490)::numeric, 2),
    1000000,   -- stock alto: las pruebas de carga no deben agotarlo
    'Producto de prueba número ' || n || ' para las pruebas de carga del balanceador.'
FROM generate_series(1, 2000) AS n;

INSERT INTO users (username, salt, pass_hash)
SELECT
    'usuario' || n,
    md5('sal-' || n),
    encode(digest(md5('sal-' || n) || 'clave123', 'sha256'), 'hex')
FROM generate_series(1, 1000) AS n;

ANALYZE;
