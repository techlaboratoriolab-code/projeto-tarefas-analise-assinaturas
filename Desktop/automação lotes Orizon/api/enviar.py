from http.server import BaseHTTPRequestHandler
import json
import base64
import hashlib
import re
from datetime import datetime
from xml.etree import ElementTree as ET
import requests
import time

# CREDENCIAIS FIXAS (do seu código)
CODIGO_PRESTADOR = "0000263036"
LOGIN = "LAB0186"
SENHA = "91a2ab8fbdd7884f7e32fd19694712a0"
REGISTRO_ANS = "005711"


class OrizonTISSEnvio:
    def __init__(self, codigo_prestador, login, senha, registro_ans="005711"):
        self.url = "https://tiss-documentos.orizon.com.br/Service.asmx"
        self.codigo_prestador = codigo_prestador
        self.login = login
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
            numero_lote, numero_protocolo, numero_guia_prestador,
            numero_guia_operadora, numero_documento, pdf_base64,
            natureza_guia, tipo_documento, observacao
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
    def __init__(self, xml_content, pdfs_base64_dict):
        self.xml_content = xml_content
        self.pdfs_base64_dict = pdfs_base64_dict
        self.pacientes = []
        
    def extrair_pacientes(self):
        try:
            root = ET.fromstring(self.xml_content)
        except Exception as e:
            return {'error': f'Erro ao processar XML: {str(e)}'}
        
        numero_lote = self._extrair_texto(root, './/numeroLote')
        
        guias_encontradas = []
        elementos_processados = set()
        
        for elem in root.iter():
            tag_limpa = elem.tag.split('}')[1] if '}' in elem.tag else elem.tag
            tag_lower = tag_limpa.lower()
            
            if 'guia' in tag_lower and id(elem) not in elementos_processados:
                tem_dados = False
                for child in elem.iter():
                    child_tag = (child.tag.split('}')[1] if '}' in child.tag else child.tag).lower()
                    if any(x in child_tag for x in ['numeroguia', 'numerocarteira', 'carteirinha']) and child.text and child.text.strip():
                        tem_dados = True
                        break
                
                if tem_dados:
                    guias_encontradas.append(elem)
                    elementos_processados.add(id(elem))
        
        for guia in guias_encontradas:
            paciente = self._extrair_dados_guia(guia, numero_lote)
            if paciente:
                self.pacientes.append(paciente)
        
        return self.pacientes
    
    def _extrair_texto(self, elemento, xpath):
        def remover_namespace(tag):
            if '}' in tag:
                return tag.split('}')[1]
            return tag
        
        for elem in elemento.iter():
            tag = remover_namespace(elem.tag).lower()
            xpath_limpo = xpath.replace('.//', '').replace('./', '').lower()
            if tag == xpath_limpo and elem.text:
                return elem.text.strip()
        return None
    
    def _extrair_dados_guia(self, guia, numero_lote):
        def remover_namespace(tag):
            if '}' in tag:
                return tag.split('}')[1]
            return tag
        
        paciente = {'numeroLote': numero_lote}
        
        for elem in guia.iter():
            tag = remover_namespace(elem.tag).lower()
            texto = elem.text.strip() if elem.text and elem.text.strip() else None
            
            if not texto:
                continue
            
            if 'numeroguiaprestador' in tag:
                paciente['numeroGuiaPrestador'] = texto
            elif 'numeroguiaoperadora' in tag:
                paciente['numeroGuiaOperadora'] = texto
            elif 'numeroguia' in tag and 'numeroGuiaPrestador' not in paciente:
                paciente['numeroGuiaPrestador'] = texto
            elif 'numerocarteira' in tag or 'carteirinha' in tag:
                paciente['carteirinha'] = texto
            elif 'numeroprotocolo' in tag or 'protocolo' in tag:
                paciente['numeroProtocolo'] = texto
            elif 'nomebeneficiario' in tag:
                paciente['nome'] = texto
            elif 'numerodocumento' in tag:
                paciente['numeroDocumento'] = texto
        
        if not paciente.get('numeroDocumento'):
            if paciente.get('numeroGuiaPrestador'):
                paciente['numeroDocumento'] = f"{paciente['numeroGuiaPrestador']}001"
        
        if paciente.get('numeroGuiaPrestador') or paciente.get('numeroGuiaOperadora'):
            return paciente
        
        return None
    
    def processar_envios(self, cliente_orizon):
        if not self.pacientes:
            self.extrair_pacientes()
        
        if not self.pacientes:
            return {'error': 'Nenhum paciente encontrado no XML'}
        
        resultados = []
        
        for paciente in self.pacientes:
            numero_guia = paciente.get('numeroGuiaPrestador', '')
            
            # Busca o PDF no dicionário enviado
            # Formato esperado: "357174867_GUIA_doc1.pdf" ou só "357174867"
            pdf_base64 = None
            for key in self.pdfs_base64_dict.keys():
                if numero_guia in key:
                    pdf_base64 = self.pdfs_base64_dict[key]
                    break
            
            if not pdf_base64:
                resultados.append({
                    'paciente': paciente,
                    'status': 'PDF não encontrado',
                    'success': False
                })
                continue
            
            resultado = cliente_orizon.enviar_documento(
                numero_lote=paciente.get('numeroLote', ''),
                numero_protocolo=paciente.get('numeroProtocolo', ''),
                numero_guia_prestador=paciente.get('numeroGuiaPrestador', ''),
                numero_guia_operadora=paciente.get('numeroGuiaOperadora', ''),
                numero_documento=paciente.get('numeroDocumento', ''),
                pdf_base64=pdf_base64,
                natureza_guia='2',
                tipo_documento='01',
                observacao=''
            )

            resultados.append({
                'paciente': paciente,
                'status': 'Enviado' if resultado['success'] else 'Erro',
                'success': resultado['success'],
                'resposta': resultado
            })
            
            time.sleep(2)
        
        return resultados


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        try:
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
            # Recebe: xml_content (string) e pdfs (dict com {nomeArquivo: base64})
            if 'xml_content' not in data or 'pdfs' not in data:
                self.send_error_response('Envie xml_content e pdfs {nomeArquivo: base64}', 400)
                return
            
            cliente = OrizonTISSEnvio(CODIGO_PRESTADOR, LOGIN, SENHA, REGISTRO_ANS)
            processador = ProcessadorXMLTISS(data['xml_content'], data['pdfs'])
            
            resultados = processador.processar_envios(cliente)
            
            if isinstance(resultados, dict) and 'error' in resultados:
                self.send_error_response(resultados['error'], 400)
                return
            
            sucessos = sum(1 for r in resultados if r.get('success'))
            
            self.send_json_response({
                'success': True,
                'total': len(resultados),
                'sucessos': sucessos,
                'falhas': len(resultados) - sucessos,
                'resultados': resultados
            })
            
        except json.JSONDecodeError:
            self.send_error_response('JSON inválido', 400)
        except Exception as e:
            self.send_error_response(f'Erro interno: {str(e)}', 500)
    
    def send_json_response(self, data, status=200):
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode('utf-8'))
    
    def send_error_response(self, message, status=400):
        self.send_json_response({'success': False, 'error': message}, status)
