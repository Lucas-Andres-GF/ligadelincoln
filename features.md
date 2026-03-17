# Features

## DATOS EN LA BASE DE DATOS:

## Torneos del 2026.

- Torneo Apertura 2026
- Torneo Clausura 2026
- Primavera/Verano 2026

## Existen las siguientes divisiones:

- Primera División
- Septima División
- Octava División
- Novena División
- Decima División

## Secciones que debe tener la página:

- Página principal:
  - Header con Liga De Lincoln - Nav(Primera Septima Octava Novena Decima (Hacerlo hamburguesa para que se vea bien en mobile)).
  - Mostrar el fixture de la primera división.
  - Mostrar la tabla de posiciones de la primera división.

- Para acceder a toda la información de cada división, se debe hacer click en el nombre de la división (ejemplo: "Primera División") y ahí mostrar toda la información de esa división.

- De cada división se debe mostrar:
  - Alineaciones
  - Fixture de cada división.
    - Mostrar: Fecha, Hora, Estado, Local, EscudoLocal, golesLocal,golesVisitante, EscudoVisitante, Visitante.
    - Observación: Un club queda "Libre" por fecha (depende la categoriad), por lo que se debe mostrar esa información.
    - Ademas guardar: Arbitro, Cancha.
  - Tabla de posiciones de cada división.
    - Mostrar: Posición, Equipo, PTS, PJ, PG, PE, PP, GF, GC, DIF, ULTIMOS (V, E, D).
  - Goleadores de cada división.
    - Mostrar: Escudo, Nombre, Goles.
  - Valla menos vencida de cada división.
    - Guardar (por ahora no voy a mostrar): Escudo, Nombre, Goles en contra.
  - Tarjetas rojas de cada división.
    - Guardar (por ahora no voy a mostrar): Escudo, Nombre, Tarjetas rojas.
  - Tarjetas amarillas de cada división.
    - Guardar (por ahora no voy a mostrar): Escudo, Nombre, Tarjetas amarillas.

## Cada club, al tocarlo, debe mostrar toda la información de ese club:

- Hero: Banner de una imagen de la entrada al club. sobre el banner se muestra: Escudo, nombre del club, ciudad.
- Debe tener un selecctor de categoria. (por defeto se muestra la primera división, pero se puede cambiar a septima, octava, novena o decima).
- Mostrar el fixture del club (de la categoria que se haya seleccionado).
- Mostrar la tabla de posiciones del club (de la categoria que se haya seleccionado).
- Mostrar los goleadores del club (de la categoria que se haya seleccionado).
- Mostrar la valla menos vencida del club (de la categoria que se haya seleccionado).
- Mostrar las tarjetas rojas del club (de la categoria que se haya seleccionado).
- Mostrar las tarjetas amarillas del club (de la categoria que se haya seleccionado).

## De cada partido, al tocarlo, debe mostrar toda la información de ese partido:

- Hero: izq: EscudoLocal, Local (debajo el escudo), medio: Hora (si aun no se juego), Fecha, Estado, (golesLocal - golesVisitante (si ya se jugo)), der: EscudoVisitante, Visitante (debajo el escudo).
- Mostrar la alineación de cada equipo.
- Mostrar el arbitro y la cancha.

## BASE DE DATOS:

- Tablas:
  - Torneos
    - Id (autoincrementable)
    - Created_at(timestamp)
    - nombre
    - año

  - Equipos
    - Id (autoincrementable)
    - Created_at(timestamp)
    - nombre
    - escudo_url
    - ciudad
    - banner_url

  - Partidos
    - Id (autoincrementable)
    - Created_at(timestamp)
    - numero_fecha (ejemplo: fecha 1, fecha 2, fecha 3, etc)
    - fecha
    - hora
    - local_id (foreign key a equipos)
    - goles_local
    - visitante_id (foreign key a equipos)
    - goles_visitante
    - estado (pendiente, jugado, suspendido, etc)
    - arbitro
    - cancha
    - observaciones (ejemplo: "Libre")

  - Posiciones
    - Id (autoincrementable)
    - Created_at(timestamp)
    - equipo_id (foreign key a equipos)
    - puntos
    - partidos_jugados
    - partidos_ganados
    - partidos_empatados
    - partidos_perdidos
    - goles_favor
    - goles_contra
    - diferencia_goles
    - ultimos_resultados (string con los ultimos 5 resultados, ejemplo: "V,E,D,V,V")
  - Goleadores
    - Id (autoincrementable)
    - Created_at(timestamp)
    - equipo_id (foreign key a equipos)
    - nombre_jugador
    - goles
  - VallaMenosVencida
    - Id (autoincrementable)
    - Created_at(timestamp)
    - equipo_id (foreign key a equipos)
    - nombre_jugador
    - goles_en_contra

  - TarjetasRojas
    - Id (autoincrementable)
    - Created_at(timestamp)
    - equipo_id (foreign key a equipos)
    - nombre_jugador
    - tarjetas_rojas

  - TarjetasAmarillas
    - Id (autoincrementable)
    - Created_at(timestamp)
    - equipo_id (foreign key a equipos)
    - nombre_jugador
    - tarjetas_amarillas
