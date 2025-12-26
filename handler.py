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
        url = f'https://mindicador.cl/api/{self.indicador}/{self.year}'
        response = requests.get(url)
        data = json.loads(response.text.encode("utf-8"))
        return data

# Configuración de recursos
IS_OFFLINE = os.environ.get('IS_OFFLINE')

if IS_OFFLINE:
    print("Entorno local detectado. Configurando recursos offline.")
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
    print("Iniciando solicitud de UF...")
    
    try:
        year_actual = datetime.now().year
        mi_indicador = Mindicador('uf', year_actual)
        data = mi_indicador.InfoApi()

        hoy = datetime.now().strftime('%Y-%m-%d')
        # Buscar el valor de hoy en la lista
        item_hoy = next((item for item in data['serie'] if item['fecha'][:10] == hoy), None )

        if item_hoy:
            valor_uf = item_hoy['valor']
            fecha_uf = item_hoy['fecha'][:10]
        else:
            print(f"Advertencia: No se encontró valor para {hoy}. Usando último disponible.")
            valor_uf = data['serie'][0]['valor']
            fecha_uf = data['serie'][0]['fecha'][:10]  
        
        print(f"Valor UF recuperado: {valor_uf} con fecha {fecha_uf}")

        # Generar PDF
        print("Generando archivo PDF temporal...")
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Arial", size=12)
        pdf.cell(200, 10, txt=f"Valor UF: {valor_uf}", ln=1, align="C")
        pdf.cell(200, 10, txt=f"Fecha: {fecha_uf}", ln=2, align="C")
        
        nombre_archivo = f"UF_{fecha_uf}.pdf"
        path_temporal = tempfile.gettempdir()
        ruta_temporal = os.path.join(path_temporal, nombre_archivo)
        pdf.output(ruta_temporal)

        # Subir a S3
        print(f"Subiendo {nombre_archivo} al bucket {BUCKET_NAME}...")
        s3.upload_file(ruta_temporal, BUCKET_NAME, nombre_archivo)
        
        if IS_OFFLINE:
            url_pdf = f"http://localhost:4569/{BUCKET_NAME}/{nombre_archivo}"
        else:
            url_pdf = f"https://{BUCKET_NAME}.s3.amazonaws.com/{nombre_archivo}"

        # Guardar en DynamoDB
        print("Guardando registro en base de datos...")
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

        print("Proceso UF finalizado correctamente. Status: 200")

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Proceso UF OK", "data": item})
        }

    except Exception as e:
        print(f"Error crítico en obtener_uf: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}


def obtener_dolar(event, context):
    print("Ejecutando cron job: Dolar diario...")

    try:
        year_actual = datetime.now().year
        mi_indicador = Mindicador('dolar', year_actual)
        data = mi_indicador.InfoApi()
        
        valor_dolar = data['serie'][0]['valor']
        fecha_dolar = data['serie'][0]['fecha'][:10]
        
        print(f"Valor Dolar recuperado: {valor_dolar}")

        print("Actualizando DynamoDB...")
        table = dynamodb.Table(TABLE_NAME)
        item = {
            'id': f"DOLAR-{fecha_dolar}",
            'fecha': fecha_dolar,
            'tipo': 'DOLAR',
            'valor': str(valor_dolar),
            'timestamp': datetime.now().isoformat()
        }
        table.put_item(Item=item)

        print("Cron finalizado con éxito. Status: 200")

        return {
            "statusCode": 200,
            "body": json.dumps({"message": "Dólar guardado OK", "data": item})
        }

    except Exception as e:
        print(f"Error en cron dolar: {str(e)}")
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}
    

def obtener_datos(event, context):
    try:
        print("Consultando historial completo de indicadores...")
        table = dynamodb.Table(TABLE_NAME)
        response = table.scan()
        items = response.get('Items', [])
        
        items_ordenados = sorted(items, key=lambda x: x.get('fecha', ''), reverse=True)
        
        print(f"Registros encontrados: {len(items_ordenados)}")

        return {
            "statusCode": 200,
            "headers": {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Credentials": True,
            },
            "body": json.dumps(items_ordenados)
        }

    except Exception as e:
        print(f"Error al leer DynamoDB: {str(e)}")
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)})
        }