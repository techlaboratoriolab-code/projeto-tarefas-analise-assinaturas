from http.server import BaseHTTPRequestHandler
import json
import base64
import hashlib
import re
from datetime import datetime
from xml.etree import ElementTree as ET
import requests
import time


class OrizonTISSEnvio:
    def __init__(self, codigo_prestador, login, senha, registro_ans="005711"):
        """
        Inicializa o cliente de envio TISS Orizon
        """
        self.url = "https://tiss-documentos.orizon.com.br/Service.asmx"
        self.codigo_prestador = codigo_prestador
        self.login = login
        # Se a senha já vier em MD5 (32 hex), usa como está; senão, aplica MD5 uma vez
        senha_str = (senha or "").strip()
        if re.fullmatch(r"[A-Fa-f0-9]{32}", senha_str):
            self.senha_md5 = senha_str.lower()
        else:
            self.senha_md5 = hashlib.md5(senha_str.encode("utf-8")).hexdigest().lower()
        self.registro_ans = registro_ans
        
    def criar_xml_envio(self, numero_lote, numero_protocolo, numero_guia_prestador, 
                        numero_guia_operadora, numero_documento, pdf_base64, 
                        natureza_guia="2", tipo_documento="01", observacao=""):
        """
        Cria o XML de envio no formato TISS Orizon
        """
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
        """
        Envia um documento para o webservice TISS Orizon com retry automático
        """
        # Cria o XML
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

        # Headers da requisição
        headers = {
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': 'http://www.ans.gov.br/padroes/tiss/schemas/envioDocumentoWS'
        }

        # Tenta enviar com retry automático
        ultimo_erro = None
        for tentativa in range(1, max_tentativas + 1):
            try:
                if tentativa > 1:
                    time.sleep(2)  # Aguarda 2s antes de tentar novamente

                response = requests.post(
                    self.url,
                    data=xml_string.encode('utf-8'),
                    headers=headers,
                    timeout=120
                )

                sucesso = response.status_code == 200

                return {
                    'success': sucesso,
                    'status_code': response.status_code,
                    'response': response.text,
                    'tentativas': tentativa
                }

            except requests.exceptions.Timeout:
                ultimo_erro = 'Timeout na requisição'
                continue
            except requests.exceptions.SSLError as e:
                ultimo_erro = f'Erro SSL: {str(e)[:100]}'
                continue
            except requests.exceptions.ConnectionError as e:
                ultimo_erro = f'Erro de conexão: {str(e)[:100]}'
                continue
            except Exception as e:
                ultimo_erro = str(e)[:100]
                continue

        # Se chegou aqui, todas as tentativas falharam
        return {
            'success': False,
            'error': f'Falhou após {max_tentativas} tentativas. Último erro: {ultimo_erro}',
            'tentativas': max_tentativas
        }


class ProcessadorXMLTISS:
    """
    Processa o XML TISS LOTE DE GUIAS e extrai dados para envio de documentos
    """
    
    def __init__(self, xml_content):
        self.xml_content = xml_content
        self.pacientes = []
        
    def extrair_pacientes(self):
        """
        Extrai dados dos pacientes do XML TISS (lote de guias)
        """
        try:
            root = ET.fromstring(self.xml_content)
        except Exception as e:
            return {'error': f'Erro ao processar XML: {str(e)}'}
        
        # Extrai o número do lote
        numero_lote = self._extrair_texto(root, './/numeroLote', 'Número do lote')
        
        # Debug: listar todas as tags do XML
        tags_encontradas = []
        for elem in root.iter():
            tag_limpa = elem.tag.split('}')[1] if '}' in elem.tag else elem.tag
            if tag_limpa not in tags_encontradas:
                tags_encontradas.append(tag_limpa)
        
        # Busca TODAS as guias usando XPath mais robusto
        guias_encontradas = []
        
        # Procura por padrões comuns de guias
        padroes = [
            './/*[contains(local-name(), "guia")]',
            './/*[local-name()="guiaConsulta"]',
            './/*[local-name()="guiaSP-SADT"]',
            './/*[local-name()="guiaSADT"]',
            './/*[local-name()="guiaResumoInternacao"]',
            './/*[local-name()="guiaHonorarioIndividual"]',
            './/*[local-name()="guiaTratamentoOdontologico"]',
            './/*[local-name()="guiaOdontologia"]',
            './/*[local-name()="guiaInternacao"]'
        ]
        
        elementos_processados = set()
        
        # Primeiro tenta com contains - mais abrangente
        for elem in root.iter():
            tag_limpa = elem.tag.split('}')[1] if '}' in elem.tag else elem.tag
            tag_lower = tag_limpa.lower()
            
            # Se a tag contém "guia" e tem filhos com dados de paciente
            if 'guia' in tag_lower and id(elem) not in elementos_processados:
                # Verifica se tem dados relevantes (numeroGuia ou numeroCarteira)
                tem_dados = False
                for child in elem.iter():
                    child_tag = (child.tag.split('}')[1] if '}' in child.tag else child.tag).lower()
                    if any(x in child_tag for x in ['numeroguia', 'numerocarteira', 'carteirinha']) and child.text and child.text.strip():
                        tem_dados = True
                        break
                
                if tem_dados:
                    guias_encontradas.append(elem)
                    elementos_processados.add(id(elem))
        
        # Processa cada guia
        for guia in guias_encontradas:
            paciente = self._extrair_dados_guia(guia, numero_lote)
            if paciente:
                self.pacientes.append(paciente)
        
        return self.pacientes
    
    def _extrair_texto(self, elemento, xpath, descricao=""):
        """
        Extrai texto de um elemento via xpath
        """
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
        """
        Extrai dados de uma guia específica
        """
        def remover_namespace(tag):
            if '}' in tag:
                return tag.split('}')[1]
            return tag
        
        paciente = {
            'numeroLote': numero_lote
        }
        
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
            
            # Validação dos dados recebidos
            required_fields = ['codigo_prestador', 'login', 'senha']
            for field in required_fields:
                if field not in data:
                    self.send_error_response(f'Campo obrigatório ausente: {field}', 400)
                    return
            
            # Cria o cliente Orizon
            cliente = OrizonTISSEnvio(
                codigo_prestador=data['codigo_prestador'],
                login=data['login'],
                senha=data['senha'],
                registro_ans=data.get('registro_ans', '005711')
            )
            
            # Se enviou XML para processar
            if 'xml_content' in data:
                processador = ProcessadorXMLTISS(data['xml_content'])
                pacientes = processador.extrair_pacientes()
                
                self.send_json_response({
                    'success': True,
                    'message': f'XML processado com sucesso',
                    'total_pacientes': len(pacientes),
                    'pacientes': pacientes
                })
                return
            
            # Se enviou dados para envio direto
            if 'pdf_base64' in data:
                resultado = cliente.enviar_documento(
                    numero_lote=data.get('numero_lote', ''),
                    numero_protocolo=data.get('numero_protocolo', ''),
                    numero_guia_prestador=data.get('numero_guia_prestador', ''),
                    numero_guia_operadora=data.get('numero_guia_operadora', ''),
                    numero_documento=data.get('numero_documento', ''),
                    pdf_base64=data['pdf_base64'],
                    natureza_guia=data.get('natureza_guia', '2'),
                    tipo_documento=data.get('tipo_documento', '01'),
                    observacao=data.get('observacao', ''),
                    max_tentativas=data.get('max_tentativas', 3)
                )
                
                self.send_json_response({
                    'success': resultado['success'],
                    'resultado': resultado
                })
                return
            
            self.send_error_response('Nenhuma ação especificada (xml_content ou pdf_base64)', 400)
            
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
        self.send_json_response({
            'success': False,
            'error': message
        }, status)
