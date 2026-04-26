from fastapi import FastAPI
import mysql.connector
from dotenv import load_dotenv
import os

load_dotenv()

app = FastAPI()

DB_CONFIG = {
    "host": os.getenv("DB_HOST"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME")
}
print("Mis credenciales cargadas son:", DB_CONFIG)
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