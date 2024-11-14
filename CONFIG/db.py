import mysql.connector
import os
from dotenv import load_dotenv

load_dotenv()

# Função para conectar ao banco de dados
def get_db_connection():
    try:
        db = mysql.connector.connect(
            host = os.getenv("DB_HOST"),
            user = os.getenv("DB_USER"),
            password = os.getenv("DB_PASSWORD"),
            database = os.getenv("DB_NAME")
        )
        return db
    except mysql.connector.Error as err:
        print(f"Erro ao conectar ao banco de dados: {err}")
        return None