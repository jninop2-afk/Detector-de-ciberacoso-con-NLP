# Acta de pruebas de aceptación

**Proyecto:** Detector de ciberacoso con NLP (bots de Discord y Bluesky)
**Versión evaluada:** rama / commit `__________`
**Fecha:** `__________`

Las pruebas de aceptación verifican que el sistema hace lo que el **cliente**
pidió. Cada historia de usuario tiene criterios de aceptación escritos en
`features/*.feature` (Gherkin). Se validan en dos partes:

1. **Automática:** `pytest -v tests/aceptacion` ejecuta todos los escenarios.
2. **Con el cliente (UAT):** el cliente repite los escenarios en Discord y
   Bluesky reales, guiado por el protocolo de `tests/sistema/PLAN_PRUEBAS_SISTEMA.md`,
   y decide si acepta cada historia.

## Participantes

| Rol | Nombre | Firma |
|---|---|---|
| Cliente / docente evaluador | | |
| Moderador de Discord (usuario final) | | |
| Usuario de Bluesky (usuario final) | | |
| Equipo de desarrollo | | |

## Historias de usuario

| ID | Como… | quiero… | para… | Escenarios | Automática | Validación del cliente | ¿Aceptada? | Observaciones |
|---|---|---|---|---|---|---|---|---|
| HU-01 | moderador de Discord | que un insulto se borre y se me informe en privado | proteger a los miembros sin exponer a nadie | 1 | ☐ Pasa | CS-M04 | ☐ Sí ☐ No | |
| HU-02 | moderador de Discord | que las conversaciones normales no se toquen | no molestar a la comunidad | 1 | ☐ Pasa | CS-M03 | ☐ Sí ☐ No | |
| HU-03 | moderador de Discord | que quien reincide 4 veces seguidas quede bloqueado | frenar el acoso persistente | 1 | ☐ Pasa | CS-M05, CS-M06 | ☐ Sí ☐ No | |
| HU-04 | moderador de Discord | decidir yo los casos dudosos | evitar sanciones injustas | 1 | ☐ Pasa | CS-M08, CS-M09 | ☐ Sí ☐ No | |
| HU-05 | usuario de Bluesky | preguntarle al bot si un mensaje es acoso | saber cómo reaccionar | 1 | ☐ Pasa | CS-M20, CS-M21 | ☐ Sí ☐ No | |
| HU-06 | usuario de Bluesky | que el bot vigile las respuestas a mis posts | no tener que leer el acoso yo | 1 | ☐ Pasa | CS-M24, CS-M25 | ☐ Sí ☐ No | |
| HU-07 | usuario de Bluesky | poder desactivar la vigilancia | controlar mi privacidad | 1 | ☐ Pasa | CS-M26 | ☐ Sí ☐ No | |
| HU-08 | equipo del proyecto | que los reportes sean simulados mientras se prueba | no reportar cuentas por error | 1 | ☐ Pasa | CS-M23 | ☐ Sí ☐ No | |
| HU-09 | responsable del proyecto | que se reconozca cada tipo de acoso | aplicar la sanción adecuada | 5 | ☐ Pasa | Prueba con mensajes propuestos por el cliente | ☐ Sí ☐ No | |
| HU-10 | responsable del proyecto | que disfrazar el insulto no evite la detección | que no se burle el sistema | 5 | ☐ Pasa | Ídem | ☐ Sí ☐ No | |
| HU-11 | responsable del proyecto | un acierto mínimo del 90 % (binario) y 85 % (categoría) | sanciones justas | 1 | ☐ Pasa | Revisar `reportes/caja_negra_detector.csv` | ☐ Sí ☐ No | |
| HU-12 | moderador de Discord | que la respuesta sea en tiempo real | actuar antes de que el acoso se lea | 1 | ☐ Pasa | Observación en CS-M04 | ☐ Sí ☐ No | |

## Prueba libre del cliente

El cliente escribe **10 mensajes propios** (5 ofensivos y 5 normales) con
`/analizar` en Discord o `python main.py cli`, y anota si está de acuerdo con
el resultado.

| # | Mensaje del cliente | Resultado del sistema | ¿De acuerdo? |
|---|---|---|---|
| 1 | | | ☐ Sí ☐ No |
| 2 | | | ☐ Sí ☐ No |
| 3 | | | ☐ Sí ☐ No |
| 4 | | | ☐ Sí ☐ No |
| 5 | | | ☐ Sí ☐ No |
| 6 | | | ☐ Sí ☐ No |
| 7 | | | ☐ Sí ☐ No |
| 8 | | | ☐ Sí ☐ No |
| 9 | | | ☐ Sí ☐ No |
| 10 | | | ☐ Sí ☐ No |

**Criterio:** se acepta si el cliente está de acuerdo en al menos 8 de 10.

## Limitaciones conocidas (informadas al cliente)

- Un agradecimiento puede clasificarse por error como insulto (hallazgo CN-DET-004).
- La difamación a políticos sin insultos explícitos puede no detectarse (CN-DET-026).
- Una mención sola (`@usuario`) se envía a revisión humana (CN-ROB-006).
- Las pruebas automáticas usan sólo el modelo clásico; RoBERTa puede mejorar los casos dudosos.

## Decisión

☐ **Aceptado** · ☐ **Aceptado con observaciones** · ☐ **No aceptado**

Observaciones y acciones pendientes:

&nbsp;

Firma del cliente: ____________________  Fecha: ____________
