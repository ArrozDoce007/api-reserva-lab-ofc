from dotenv import load_dotenv
import os
import boto3

load_dotenv()

# Configurações do S3
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_S3_BUCKET_NAME = os.getenv("AWS_S3_BUCKET_NAME")

s3_client = boto3.client(
    's3',
    aws_access_key_id=AWS_ACCESS_KEY_ID,
    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
    region_name='us-east-2'
)

def allowed_file(filename):
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg'}
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_to_s3(file_obj, bucket_name, file_name):
    try:
        s3_client.upload_fileobj(file_obj, bucket_name, file_name)
        file_url = f"https://{bucket_name}.s3.amazonaws.com/{file_name}"
        return file_url
    except Exception as e:
        print(f"Erro ao fazer upload para o S3: {e}")
        return None

def check_image_exists(bucket_name, filename):
    try:
        s3_client.head_object(Bucket=bucket_name, Key=filename)
        return True  # A imagem já existe
    except Exception as e:
        if e.response['Error']['Code'] == '404':
            return False  # A imagem não existe
        else:
            print(f'Erro ao verificar a imagem no S3: {e}')
            return False

def delete_from_s3(bucket_name, file_name):
    try:
        s3_client.delete_object(Bucket=bucket_name, Key=file_name)
        print(f"Imagem {file_name} deletada do S3 com sucesso.")
    except Exception as e:
        print(f"Erro ao deletar a imagem do S3: {e}")

# Função para substituir espaços por underscore
def format_filename(filename):
    return filename.replace(' ', '_').replace('-', '_')

# Busca a imagem atinga
def get_old_image_url(cursor, lab_id):
    cursor.execute("SELECT image FROM Laboratorios WHERE id = %s", (lab_id,))
    result = cursor.fetchone()
    return result[0] if result else None