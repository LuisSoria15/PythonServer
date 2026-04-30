from fastapi import FastAPI
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