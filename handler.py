import json
import boto3
import requests
import os
import tempfile
from fpdf import FPDF
from datetime import datetime

class Mindicador:
    def __init__(self, indicador, year):
        self.indicador = indicador
        self.year = year
 
    def InfoApi(self):
        try:
            url = f'https://mindicador.cl/api/{self.indicador}/{self.year}'
            response = requests.get(url, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error conectando a la API: {e}")
            raise e

# Configuración de recursos (Local vs Cloud)
IS_OFFLINE = os.environ.get('IS_OFFLINE')

if IS_OFFLINE:
    dynamodb = boto3.resource(
        'dynamodb',
        region_name='localhost',
        endpoint_url='http://localhost:8000',
        aws_access_key_id='DEFAULT',
        aws_secret_access_key='DEFAULT'
    )
    s3 = boto3.client(
        's3',
        region_name='us-east-1',
        endpoint_url='http://localhost:4569',
        aws_access_key_id='S3RVER',
        aws_secret_access_key='S3RVER'
    )
else:
    dynamodb = boto3.resource('dynamodb')
    s3 = boto3.client('s3')

TABLE_NAME = os.environ.get('DYNAMODB_TABLE', 'edarkstore-indicators')
BUCKET_NAME = os.environ.get('S3_BUCKET', 'edarkstore-bucket')


def obtener_uf(event, context):
    print("Iniciando proceso UF...")
    
    try:
        year_actual = datetime.now().year
        mi_indicador = Mindicador('uf', year_actual)
        data = mi_indicador.InfoApi()

        hoy = datetime.now().strftime('%Y-%m-%d')
        valor_uf = None
        fecha_uf = None

        # Buscar fecha exacta de hoy
        for item in data['serie']:
            if item['fecha'].startswith(hoy):
                valor_uf = item['valor']
                fecha_uf = item['fecha'][:10]
                break
        
        # Fallback: Usar último valor disponible si no hay dato de hoy
        if not valor_uf:
            print(f"No se encontró UF para {hoy}, usando último valor.")
            valor_uf = data['serie'][0]['valor']
            fecha_uf = data['serie'][0]['fecha'][:10]

        # Generar PDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Valor UF: {valor_uf}", ln=1, align="C")
        pdf.cell(200, 10, txt=f"Fecha: {fecha_uf}", ln=2, align="C")
        
        nombre_archivo = f"UF_{fecha_uf}.pdf"
        ruta_temporal = os.path.join(tempfile.gettempdir(), nombre_archivo)
        pdf.output(ruta_temporal)

        # Subir a S3
        s3.upload_file(ruta_temporal, BUCKET_NAME, nombre_archivo)
        
        if IS_OFFLINE:
            url_pdf = f"http://localhost:4569/{BUCKET_NAME}/{nombre_archivo}"
        else:
            url_pdf = f"https://{BUCKET_NAME}.s3.amazonaws.com/{nombre_archivo}"

        # Guardar en DynamoDB
        table = dynamodb.Table(TABLE_NAME)
        item = {
            'id': f"UF-{fecha_uf}",
            'fecha': fecha_uf,
            'tipo': 'UF',
            'valor': str(valor_uf),
            'url_pdf': url_pdf,
            'timestamp': datetime.now().isoformat()
        }
        table.put_item(Item=item)

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Proceso UF OK", "data": item})
        }

    except Exception as e:
        print(f"Error en obtener_uf: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def obtener_dolar(event, context):
    print("Iniciando proceso Dolar...")

    try:
        year_actual = datetime.now().year
        mi_indicador = Mindicador('dolar', year_actual)
        data = mi_indicador.InfoApi()
        
        # Obtener el valor más reciente
        dato_reciente = data['serie'][0]
        valor_dolar = dato_reciente['valor']
        fecha_dolar = dato_reciente['fecha'][:10] 
        
        table = dynamodb.Table(TABLE_NAME)
        item = {
            'id': f"DOLAR-{fecha_dolar}",
            'fecha': fecha_dolar,
            'tipo': 'DOLAR',
            'valor': str(valor_dolar),
            'timestamp': datetime.now().isoformat()
        }
        table.put_item(Item=item)

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Dólar guardado OK", "data": item})
        }

    except Exception as e:
        print(f"Error en obtener_dolar: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def obtener_datos(event, context):
    try:
        table = dynamodb.Table(TABLE_NAME)
        response = table.scan()
        items = response.get('Items', [])
        
        # Ordenar por fecha descendente
        items_ordenados = sorted(items, key=lambda x: x.get('fecha', ''), reverse=True)
        
        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Credentials": True,
            },
            "body": json.dumps(items_ordenados)
        }

    except Exception as e:
        print(f"Error en obtener_datos: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}