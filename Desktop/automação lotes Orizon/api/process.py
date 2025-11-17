from flask import Flask, request, jsonify
import os
import base64
import hashlib
import re
from datetime import datetime
from xml.etree import ElementTree as ET
import requests
import time

app = Flask(__name__)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
    return response

class ProcessadorXMLTISS:
    def __init__(self, xml_content):
        self.xml_content = xml_content
        self.pacientes = []
        
    def _extrair_texto(self, root, xpath):
        """Extrai texto com ou sem namespace"""
        elementos = root.findall(xpath)
        if elementos and elementos[0].text:
            return elementos[0].text.strip()
        return ''
    
    def extrair_pacientes(self):
        try:
            root = ET.fromstring(self.xml_content)
        except Exception as e:
            return {'error': f'Erro ao parsear XML: {str(e)}'}
        
        # Tenta extrair com namespace
        numero_lote = self._extrair_texto(root, './/{http://www.ans.gov.br/padroes/tiss/schemas}numeroLote')
        if not numero_lote:
            numero_lote = self._extrair_texto(root, './/numeroLote')
        
        numero_protocolo = self._extrair_texto(root, './/{http://www.ans.gov.br/padroes/tiss/schemas}numeroProtocolo')
        if not numero_protocolo:
            numero_protocolo = self._extrair_texto(root, './/numeroProtocolo')
        
        # Busca guias
        guias = root.findall('.//{http://www.ans.gov.br/padroes/tiss/schemas}guiasTISS')
        if not guias:
            guias = root.findall('.//guiasTISS')
        
        for guia in guias:
            numero_guia_prestador = self._extrair_texto(guia, './/{http://www.ans.gov.br/padroes/tiss/schemas}numeroGuiaPrestador')
            if not numero_guia_prestador:
                numero_guia_prestador = self._extrair_texto(guia, './/numeroGuiaPrestador')
            
            numero_guia_operadora = self._extrair_texto(guia, './/{http://www.ans.gov.br/padroes/tiss/schemas}numeroGuiaOperadora')
            if not numero_guia_operadora:
                numero_guia_operadora = self._extrair_texto(guia, './/numeroGuiaOperadora')
            
            carteirinha = self._extrair_texto(guia, './/{http://www.ans.gov.br/padroes/tiss/schemas}numeroCarteira')
            if not carteirinha:
                carteirinha = self._extrair_texto(guia, './/numeroCarteira')
            
            if not numero_guia_prestador:
                continue
            
            paciente = {
                'numeroLote': numero_lote,
                'numeroProtocolo': numero_protocolo,
                'numeroGuiaPrestador': numero_guia_prestador,
                'numeroGuiaOperadora': numero_guia_operadora,
                'numeroDocumento': numero_guia_prestador,
                'carteirinha': carteirinha
            }
            
            self.pacientes.append(paciente)
        
        return self.pacientes


@app.route('/api/process', methods=['POST', 'OPTIONS'])
def process_xml():
    # Handle preflight
    if request.method == 'OPTIONS':
        return '', 204
    
    try:
        # Verifica se há arquivos
        if 'files' not in request.files:
            return jsonify({'error': 'Nenhum arquivo enviado'}), 400
        
        files = request.files.getlist('files')
        
        if len(files) == 0:
            return jsonify({'error': 'Nenhum arquivo enviado'}), 400
        
        resultados = []
        
        # Processa cada arquivo XML
        for file in files:
            if not file.filename.endswith('.xml'):
                resultados.append({
                    'arquivo': file.filename,
                    'error': 'Arquivo não é XML'
                })
                continue
            
            # Lê o conteúdo do XML
            xml_content = file.read().decode('utf-8')
            
            # Processa o XML
            processador = ProcessadorXMLTISS(xml_content)
            pacientes = processador.extrair_pacientes()
            
            if isinstance(pacientes, dict) and 'error' in pacientes:
                resultados.append({
                    'arquivo': file.filename,
                    'error': pacientes['error']
                })
                continue
            
            envios_resultado = []
            
            # Para cada paciente extraído
            for pac in pacientes:
                envios_resultado.append({
                    'guia': pac.get('numeroGuiaPrestador'),
                    'carteirinha': pac.get('carteirinha'),
                    'lote': pac.get('numeroLote'),
                    'protocolo': pac.get('numeroProtocolo'),
                    'guiaOperadora': pac.get('numeroGuiaOperadora'),
                    'status': '✓ Dados extraídos com sucesso'
                })
            
            resultados.append({
                'arquivo': file.filename,
                'total_pacientes': len(pacientes),
                'pacientes': envios_resultado,
                'mensagem': f'✓ XML processado! {len(pacientes)} guia(s) encontrada(s).'
            })
        
        return jsonify({
            'success': True,
            'resultados': resultados
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Handler para Vercel
def handler(request):
    with app.request_context(request.environ):
        return app.full_dispatch_request()
