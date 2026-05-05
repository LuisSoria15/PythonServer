from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import List, Dict
import json
import mysql.connector
from dotenv import load_dotenv
import os
from pydantic import BaseModel
import random
import json

load_dotenv()

app = FastAPI()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}


print("Mis credenciales cargadas son:", DB_CONFIG)


class UsuarioPuntaje(BaseModel):
    id_usuario: int
    puntaje: int
    id_categoria: int
    
class PeticionRegistro(BaseModel):
    username: str

@app.get("/categorias")
def obtener_todas_las_categorias():
    conexion = None
    
    try:
        conexion = mysql.connector.connect(**DB_CONFIG)
        cursor = conexion.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, nombre, IMAGEN
            FROM categorias
            ORDER BY id ASC
        """)

        return cursor.fetchall()

    except Exception as e:
        return {"error": str(e)}

    finally:
        if conexion and conexion.is_connected():
            cursor.close()
            conexion.close()

@app.get("/opciones/{pregunta_id}")
def obtener_opciones_por_pregunta(pregunta_id: int):
    conexion = None
    cursor = None  
    
    try:
        conexion = mysql.connector.connect(**DB_CONFIG)
        cursor = conexion.cursor(dictionary=True)
        
        # 1. Agregamos "es_correcta" a la consulta
        consulta = "SELECT id, pregunta_id, formato, contenido, es_correcta FROM opciones WHERE pregunta_id = %s"
        cursor.execute(consulta, (pregunta_id,))
        
        # 2. Usamos fetchall() para traer los 4 botones, no solo 1
        lista_opciones = cursor.fetchall()
        return lista_opciones
        
    except Exception as e:
        return {"error": str(e)}
        
    finally:
        # 3. Un finally estructurado correctamente
        if cursor:
            cursor.close()
        if conexion and conexion.is_connected():
            conexion.close()

            
@app.get("/preguntas/{categoria_id}")
def obtener_preguntas_por_categoria(categoria_id: int):
    conexion = None
    cursor = None  
    
    try:
        conexion = mysql.connector.connect(**DB_CONFIG)
        cursor = conexion.cursor(dictionary=True)
        
        #JOIN. 
        #Le ponemos "AS" a las columnas que se llaman igual (como "id" y "formato") 
        consulta = """
            SELECT 
                p.id AS p_id, p.enunciado, p.formato AS p_formato,
                o.id AS o_id, o.formato AS o_formato, o.contenido, o.es_correcta
            FROM preguntas p
            INNER JOIN opciones o ON p.id = o.pregunta_id
            WHERE p.categoria_id = %s
            ORDER BY p.id ASC
        """
        cursor.execute(consulta, (categoria_id,))
        filas_planas = cursor.fetchall()
        
        #Un diccionario temporal para agrupar
        preguntas_agrupadas = {}
        
        for fila in filas_planas:
            id_preg = fila["p_id"]
            
            #Si la pregunta no está en el diccionariola creamos con su lista vacía
            if id_preg not in preguntas_agrupadas:
                preguntas_agrupadas[id_preg] = {
                    "Id": id_preg,
                    "Enunciado": fila["enunciado"],
                    "Formato": fila["p_formato"],
                    "Opciones": [] #4 botones
                }
                
            #Metemos la opción actual en la lista de Opciones de esta pregunta
            #Convertimos es_correcta a bool() para que C# lea 'true/false' y no '1/0'
            preguntas_agrupadas[id_preg]["Opciones"].append({
                "id": fila["o_id"],
                "pregunta_id": id_preg,
                "formato": fila["o_formato"],
                "Contenido": fila["contenido"],
                "EsCorrecta": bool(fila["es_correcta"])
            })
            
        #Extraemos solo los valores y la enviamos
        lista_preguntas_anidadas = list(preguntas_agrupadas.values())
        return lista_preguntas_anidadas
        
    except Exception as e:
        return {"error": str(e)}
        
    finally:
        if cursor:
            cursor.close()
        if conexion and conexion.is_connected():
            conexion.close()
            


@app.post("/registro")
def registrar_usuario(datos: PeticionRegistro):
    conexion = None
    cursor = None
    
    try:
        conexion = mysql.connector.connect(**DB_CONFIG)
        cursor = conexion.cursor(dictionary=True)
        
        # Buscamos si el usuario ya existe usando la columna 'nombre'
        cursor.execute("SELECT id FROM usuarios WHERE nombre = %s", (datos.username,))
        usuario = cursor.fetchone()
        
        if usuario:
            # Regresamos su ID 
            return {
                "existe": True, 
                "id_usuario": usuario["id"], 
                "mensaje": "Bienvenido de vuelta"
            }
            
        
        cursor.execute("INSERT INTO usuarios (nombre) VALUES (%s)", (datos.username,))
        conexion.commit() 
        
        nuevo_id = cursor.lastrowid
        
        return {
            "existe": False, 
            "id_usuario": nuevo_id, 
            "mensaje": "Usuario nuevo registrado correctamente"
        }
        
    except Exception as e:
        if conexion and conexion.is_connected():
            conexion.rollback()
        return {"error": str(e)}
        
    finally:
        if cursor:
            cursor.close()
        if conexion and conexion.is_connected():
            conexion.close()

class GestorSalaEspera:
    def __init__(self):
        self.conexiones_activas = []
        self.votos = {} 
        self.puntajes = {}

    async def conectar(self, websocket: WebSocket, nombre: str):
        await websocket.accept()
        self.conexiones_activas.append({"ws": websocket, "nombre": nombre})

    def desconectar(self, websocket: WebSocket):
        self.conexiones_activas = [conn for conn in self.conexiones_activas if conn["ws"] != websocket]

    async def enviar_a_todos(self, mensaje: dict):
        for conexion in self.conexiones_activas:
            try:
                await conexion["ws"].send_json(mensaje)
            except Exception as e:
                # Si una compu se desconectó, que no crashee a la otra
                print(f"Error al enviar a {conexion['nombre']}: {e}")
            
    def obtener_nombres(self):
        # Saca solo los nombres para mostrarlos en la pantalla
        return [conn["nombre"] for conn in self.conexiones_activas]

    def registrar_voto(self, ws, id_categoria):
        self.votos[ws] = id_categoria

    def todos_votaron(self):
        # Si hay 4 jugadores y ya hay 4 votos registrados
        return len(self.votos) == 4 and len(self.conexiones_activas) == 4

    def obtener_ganador(self):
        conteo = {}
        # Contamos cuántos votos tiene cada categoría
        for cat in self.votos.values():
            conteo[cat] = conteo.get(cat, 0) + 1
        
        # Encontramos la cantidad máxima de votos 
        max_votos = max(conteo.values())
        
        # Guardamos en una lista las categorías que tengan ese número máximo (para ver empates)
        empatados = [cat for cat, v in conteo.items() if v == max_votos]
        
        # Si empatan, random.choice elige una al azar. Si solo hay una, simplemente devuelve esa.
        return random.choice(empatados)
    def registrar_puntaje(self, ws, nombre, puntaje):
        self.puntajes[ws] = {"nombre": nombre, "puntaje": puntaje}

    def todos_terminaron(self):
        return len(self.puntajes) == 4 and len(self.conexiones_activas) == 4

    def obtener_ganador_final(self):
        resultados = list(self.puntajes.values())
        # Ordenamos de mayor a menor puntaje
        resultados.sort(key=lambda x: x["puntaje"], reverse=True)
        return resultados

# Instanciamos el manager para que este vivo todo el tiempo
sala_manager = GestorSalaEspera()

@app.websocket("/ws/sala")
async def websocket_sala(websocket: WebSocket):
    await websocket.accept()
    try:
        nombre_jugador = await websocket.receive_text()
        sala_manager.conexiones_activas.append({"ws": websocket, "nombre": nombre_jugador})
        
        await sala_manager.enviar_a_todos({
            "accion": "actualizar_sala",
            "jugadores": sala_manager.obtener_nombres()
        })
        
        if len(sala_manager.conexiones_activas) == 4:
            await sala_manager.enviar_a_todos({
                "accion": "iniciar_juego",
                "mensaje": "¡Listos, comiencen a votar por la categoría!"
            })

        while True:
            # Ahora escuchamos los votos en formato JSON
            data = await websocket.receive_text()
            mensaje = json.loads(data)
            
            if mensaje.get("accion") == "votar":
                id_categoria = mensaje.get("id_categoria")
                sala_manager.registrar_voto(websocket, id_categoria)
                
                # Verificamos si ya tenemos los dos votos
                if sala_manager.todos_votaron():
                    ganador = sala_manager.obtener_ganador()
                    
                    # Le anunciamos el ganador a los dos jugadores a la vez
                    await sala_manager.enviar_a_todos({
                        "accion": "resultado_votacion",
                        "categoria_ganadora": ganador
                    })
                    # Limpiamos los votos por si quieren jugar otra ronda después
                    sala_manager.votos = {}
                    
            # DEJA SOLO UNA VEZ EL BLOQUE DE TERMINAR JUEGO (el que tiene los prints)
            if mensaje.get("accion") == "terminar_juego":
                nombre = mensaje.get("nombre")
                puntaje = mensaje.get("puntaje")
                sala_manager.registrar_puntaje(websocket, nombre, puntaje)
                
                # CHISMOSOS EN LA CONSOLA:
                print(f"\n--- LLEGÓ EL PUNTAJE DE: {nombre} ({puntaje} pts) ---")
                print(f"Jugadores que ya acabaron: {len(sala_manager.puntajes)}/4")
                print(f"Conexiones vivas en la sala: {len(sala_manager.conexiones_activas)}")
                
                if sala_manager.todos_terminaron():
                    print("¡LOS TRES ACABARON! Calculando ganador...")
                    resultados = sala_manager.obtener_ganador_final()
                    ganador = resultados[0]
                    empate = resultados[0]["puntaje"] == resultados[1]["puntaje"]
                    
                    print(f"El sistema eligió: {ganador['nombre']} - ¿Empate?: {empate}")
                    
                    await sala_manager.enviar_a_todos({
                        "accion": "mostrar_ganador",
                        "ganador": ganador["nombre"],
                        "puntaje_ganador": ganador["puntaje"],
                        "empate": empate,
                        "resultados": resultados
                    })
                    print("¡Mensaje de ganador enviado a las computadoras exitosamente!\n")
                    sala_manager.puntajes = {}
                    
                    
    except WebSocketDisconnect:
        sala_manager.desconectar(websocket)
        
        # Limpiamos si dejó un voto a medias
        if websocket in sala_manager.votos:
            del sala_manager.votos[websocket]
            
        # NUEVO: Limpiamos también si dejó un puntaje fantasma
        if websocket in sala_manager.puntajes:
            del sala_manager.puntajes[websocket]
            
        # Avisamos a los que queden en la sala
        await sala_manager.enviar_a_todos({
            "accion": "actualizar_sala",
            "jugadores": sala_manager.obtener_nombres()
        })


@app.put("/guardar_puntaje")
def actualizar_puntaje(datos: UsuarioPuntaje):
    conexion = None
    cursor = None
    
    try:
        conexion = mysql.connector.connect(**DB_CONFIG)
        cursor = conexion.cursor()
        
        # Hacemos UPDATE para rellenar los datos de la partida en el usuario que ya creamos
        consulta = """
            UPDATE usuarios 
            SET puntaje = %s, id_categoria = %s 
            WHERE id = %s
        """
        valores = (datos.puntaje, datos.id_categoria, datos.id_usuario)
        
        cursor.execute(consulta, valores)
        conexion.commit()
        
        return {"estatus": "exito", "mensaje": "Puntos actualizados correctamente"}
        
    except Exception as e:
        if conexion and conexion.is_connected():
            conexion.rollback()
        return {"error": str(e)}
        
    finally:
        if cursor:
            cursor.close()
        if conexion and conexion.is_connected():
            conexion.close()
            
@app.get("/leaderboard")
def obtener_leaderboard_global():
    conexion = None
    cursor = None
    try:
        conexion = mysql.connector.connect(**DB_CONFIG)
        cursor = conexion.cursor(dictionary=True)
        
        # Traemos los mejores 10 jugadores, ordenados del mayor puntaje al menor
        cursor.execute("""
            SELECT nombre, puntaje 
            FROM usuarios 
            WHERE puntaje IS NOT NULL 
            ORDER BY puntaje DESC 
            LIMIT 10
        """)
        
        return cursor.fetchall()
        
    except Exception as e:
        return {"error": str(e)}
    finally:
        if cursor: cursor.close()
        if conexion and conexion.is_connected(): conexion.close()

if __name__ == "__main__":
    import uvicorn
    # Apagamos los pings automáticos para que no los desconecte a mitad del juego
    uvicorn.run(app, host="0.0.0.0", port=11000, ws_ping_interval=None)