import os
import base64
import hashlib
import re
from datetime import datetime
from xml.etree import ElementTree as ET
from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import time

app = Flask(__name__)
CORS(app)

class OrizonTISSEnvio:
    def __init__(self, codigo_prestador, login, senha, registro_ans="005711"):
        self.url = "https://tiss-documentos.orizon.com.br/Service.asmx"
        self.codigo_prestador = codigo_prestador
        self.login = login
        
        # Validação da senha (MD5)
        senha_str = (senha or "").strip()
        if re.fullmatch(r"[A-Fa-f0-9]{32}", senha_str):
            self.senha_md5 = senha_str.lower()
        else:
            self.senha_md5 = hashlib.md5(senha_str.encode("utf-8")).hexdigest().lower()
        
        self.registro_ans = registro_ans
        
    def criar_xml_envio(self, numero_lote, numero_protocolo, numero_guia_prestador, 
                        numero_guia_operadora, numero_documento, pdf_base64, 
                        natureza_guia="2", tipo_documento="01", observacao=""):
        agora = datetime.now()
        data_registro = agora.strftime("%Y-%m-%d")
        hora_registro = agora.strftime("%H:%M:%S")
        
        xml_str = f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
xmlns:ans="http://www.ans.gov.br/padroes/tiss/schemas"
xmlns:xd="http://www.w3.org/2000/09/xmldsig#">
<soapenv:Header/>
<soapenv:Body>
<ans:envioDocumentoWS>
<ans:cabecalho>
<ans:identificacaoTransacao>
<ans:tipoTransacao>ENVIO_DOCUMENTO</ans:tipoTransacao>
<ans:sequencialTransacao>1</ans:sequencialTransacao>
<ans:dataRegistroTransacao>{data_registro}</ans:dataRegistroTransacao>
<ans:horaRegistroTransacao>{hora_registro}</ans:horaRegistroTransacao>
</ans:identificacaoTransacao>
<ans:origem>
<ans:identificacaoPrestador>
<ans:codigoPrestadorNaOperadora>{self.codigo_prestador}</ans:codigoPrestadorNaOperadora>
</ans:identificacaoPrestador>
</ans:origem>
<ans:destino>
<ans:registroANS>{self.registro_ans}</ans:registroANS>
</ans:destino>
<ans:Padrao>4.01.00</ans:Padrao>
<ans:loginSenhaPrestador>
<ans:loginPrestador>{self.login}</ans:loginPrestador>
<ans:senhaPrestador>{self.senha_md5}</ans:senhaPrestador>
</ans:loginSenhaPrestador>
</ans:cabecalho>
<ans:envioDOcumento>
<ans:numeroLote>{numero_lote}</ans:numeroLote>
<ans:numeroProtocolo>{numero_protocolo}</ans:numeroProtocolo>
<ans:numeroGuiaPrestador>{numero_guia_prestador}</ans:numeroGuiaPrestador>
<ans:numeroGuiaOperadora>{numero_guia_operadora}</ans:numeroGuiaOperadora>
<ans:numeroDocumento>{numero_documento}</ans:numeroDocumento>
<ans:naturezaGuia>{natureza_guia}</ans:naturezaGuia>
<ans:formatoDocumento>02</ans:formatoDocumento>
<ans:documento>{pdf_base64}</ans:documento>
<ans:tipoDocumento>{tipo_documento}</ans:tipoDocumento>
<ans:observacao>{observacao}</ans:observacao>
</ans:envioDOcumento>
<ans:hash>2</ans:hash>
</ans:envioDocumentoWS>
</soapenv:Body>
</soapenv:Envelope>"""
        
        return xml_str
    
    def enviar_documento(self, numero_lote, numero_protocolo, numero_guia_prestador,
                        numero_guia_operadora, numero_documento, pdf_base64,
                        natureza_guia="2", tipo_documento="01", observacao="", max_tentativas=3):
        
        xml_string = self.criar_xml_envio(
            numero_lote=numero_lote,
            numero_protocolo=numero_protocolo,
            numero_guia_prestador=numero_guia_prestador,
            numero_guia_operadora=numero_guia_operadora,
            numero_documento=numero_documento,
            pdf_base64=pdf_base64,
            natureza_guia=natureza_guia,
            tipo_documento=tipo_documento,
            observacao=observacao
        )

        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': 'http://www.ans.gov.br/padroes/tiss/schemas/envioDocumentoWS'
        }

        ultimo_erro = None
        for tentativa in range(1, max_tentativas + 1):
            try:
                if tentativa > 1:
                    time.sleep(2)

                response = requests.post(
                    self.url,
                    data=xml_string.encode('utf-8'),
                    headers=headers,
                    timeout=120
                )

                return {
                    'success': response.status_code == 200,
                    'status_code': response.status_code,
                    'response': response.text,
                    'tentativas': tentativa
                }

            except Exception as e:
                ultimo_erro = str(e)[:100]
                continue

        return {
            'success': False,
            'error': f'Falhou após {max_tentativas} tentativas. Último erro: {ultimo_erro}',
            'tentativas': max_tentativas
        }


class ProcessadorXMLTISS:
    def __init__(self, xml_content):
        self.xml_content = xml_content
        self.pacientes = []
        
    def _extrair_texto(self, root, xpath, nome_campo=''):
        elementos = root.findall(xpath)
        if elementos and elementos[0].text:
            return elementos[0].text.strip()
        return ''
    
    def extrair_pacientes(self):
        try:
            root = ET.fromstring(self.xml_content)
        except Exception as e:
            return {'error': f'Erro ao parsear XML: {str(e)}'}
        
        numero_lote = self._extrair_texto(root, './/numeroLote')
        numero_protocolo = self._extrair_texto(root, './/numeroProtocolo')
        
        guias = root.findall('.//guiasTISS')
        
        for guia in guias:
            numero_guia_prestador = self._extrair_texto(guia, './/numeroGuiaPrestador')
            numero_guia_operadora = self._extrair_texto(guia, './/numeroGuiaOperadora')
            
            # Carteirinha do beneficiário
            carteirinha = self._extrair_texto(guia, './/numeroCarteira')
            
            if not numero_guia_prestador:
                continue
            
            paciente = {
                'numeroLote': numero_lote,
                'numeroProtocolo': numero_protocolo,
                'numeroGuiaPrestador': numero_guia_prestador,
                'numeroGuiaOperadora': numero_guia_operadora,
                'numeroDocumento': numero_guia_prestador,  # Usa o número da guia como documento
                'carteirinha': carteirinha
            }
            
            self.pacientes.append(paciente)
        
        return self.pacientes


# Configurações (em produção, use variáveis de ambiente)
CODIGO_PRESTADOR = "0000263036"
LOGIN = "LAB0186"
SENHA = "91a2ab8fbdd7884f7e32fd19694712a0"
REGISTRO_ANS = "005711"


@app.route('/api/process', methods=['POST'])
def process_xml():
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
            
            # Inicializa cliente Orizon
            cliente = OrizonTISSEnvio(CODIGO_PRESTADOR, LOGIN, SENHA, REGISTRO_ANS)
            
            envios_resultado = []
            
            # Para cada paciente, tenta enviar
            # NOTA: Aqui você precisará fazer upload dos PDFs também
            # Por enquanto, vou retornar apenas os dados extraídos
            
            for pac in pacientes:
                envios_resultado.append({
                    'guia': pac.get('numeroGuiaPrestador'),
                    'carteirinha': pac.get('carteirinha'),
                    'lote': pac.get('numeroLote'),
                    'status': 'Extraído (aguardando PDF)'
                })
            
            resultados.append({
                'arquivo': file.filename,
                'total_pacientes': len(pacientes),
                'pacientes': envios_resultado
            })
        
        return jsonify({
            'success': True,
            'resultados': resultados
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'LAB TISS Processor'})


if __name__ == '__main__':
    app.run(debug=True)