from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import List, Dict
import json
import mysql.connector
from dotenv import load_dotenv
import os
from pydantic import BaseModel

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
    nombre: str
    puntaje: int
    id_categoria: int

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

@app.post("/usuarios")
def guardar_puntaje_usuario(datos_usuario: UsuarioPuntaje):
    conexion = None
    cursor = None
    
    try:
        conexion = mysql.connector.connect(**DB_CONFIG)
        cursor = conexion.cursor()
        
        #consulta INSERT. 
        consulta = """
            INSERT INTO usuarios (nombre, puntaje, id_categoria) 
            VALUES (%s, %s, %s)
        """
        #valores que llegaron desde C#
        valores = (datos_usuario.nombre, datos_usuario.puntaje, datos_usuario.id_categoria)
        
        cursor.execute(consulta, valores)
        
        
        conexion.commit()
        
        return {
            "estatus": "exito", 
            "mensaje": "Puntaje guardado correctamente",
            "id_generado": cursor.lastrowid
        }
        
    except Exception as e:
        
        if conexion and conexion.is_connected():
            conexion.rollback()
        return {"estatus": "error", "mensaje": str(e)}
        
    finally:
        if cursor:
            cursor.close()
        if conexion and conexion.is_connected():
            conexion.close()
            
class PeticionRegistro(BaseModel):
    username: str

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
            
        # Si no existe lo insertamos 
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
    def _init_(self):
        # Aqui guardaremos los tuneles de conexion y el nombre de cada jugador
        self.conexiones_activas: List[Dict[str, any]] = []

    async def conectar(self, websocket: WebSocket, nombre: str):
        await websocket.accept()
        self.conexiones_activas.append({"ws": websocket, "nombre": nombre})

    def desconectar(self, websocket: WebSocket):
        self.conexiones_activas = [conn for conn in self.conexiones_activas if conn["ws"] != websocket]

    async def enviar_a_todos(self, mensaje: dict):
        # Esta es la funcion que les habla a los 4 usuarios
        for conexion in self.conexiones_activas:
            await conexion["ws"].send_json(mensaje)
            
    def obtener_nombres(self):
        # Saca solo los nombres para mostrarlos en la pantalla
        return [conn["nombre"] for conn in self.conexiones_activas]

# Instanciamos el manager para que este vivo todo el tiempo
sala_manager = GestorSalaEspera()

@app.websocket("/ws/sala")
async def websocket_sala(websocket: WebSocket):
    # El cliente se conecta y le pedimos su nombre
    await websocket.accept()
    
    try:
        # Esperamos a que nos mande el nombre del jugador apenas se conecta
        nombre_jugador = await websocket.receive_text()
        
        # Lo metemos a la memoria de la sala
        sala_manager.conexiones_activas.append({"ws": websocket, "nombre": nombre_jugador})
        
        # Le avisamos a TODOS los conectados la lista actualizada de nombres
        nombres_actuales = sala_manager.obtener_nombres()
        await sala_manager.enviar_a_todos({
            "accion": "actualizar_sala",
            "jugadores": nombres_actuales
        })
        
        # Se inicia el juego cuando ya hay 4 usuarios
        if len(sala_manager.conexiones_activas) == 4:
            await sala_manager.enviar_a_todos({
                "accion": "iniciar_juego",
                "mensaje": "¡Listos, comienza el Kahoot!"
            })

        while True:
            data = await websocket.receive_text()
            
    except WebSocketDisconnect:
        # Si a alguien se le cierra el juego o se le va el internet
        sala_manager.desconectar(websocket)
        # Les avisamos a los que quedaron en la sala que alguien se fue
        await sala_manager.enviar_a_todos({
            "accion": "actualizar_sala",
            "jugadores": sala_manager.obtener_nombres()
        })