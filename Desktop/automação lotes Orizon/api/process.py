from http.server import BaseHTTPRequestHandler
import json
from xml.etree import ElementTree as ET


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


class handler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        try:
            # Lê o content-length
            content_length = int(self.headers.get('Content-Length', 0))

            # Lê o body
            body = self.rfile.read(content_length)

            # Verifica se é multipart/form-data
            content_type = self.headers.get('Content-Type', '')

            if 'multipart/form-data' not in content_type:
                self._send_json_response({
                    'error': 'Content-Type deve ser multipart/form-data'
                }, 400)
                return

            # Extrai o boundary
            boundary = content_type.split('boundary=')[1].encode()

            # Parse dos arquivos
            parts = body.split(b'--' + boundary)

            resultados = []

            for part in parts:
                if b'filename=' not in part:
                    continue

                # Extrai o nome do arquivo
                try:
                    filename_start = part.find(b'filename="') + 10
                    filename_end = part.find(b'"', filename_start)
                    filename = part[filename_start:filename_end].decode('utf-8')

                    if not filename.endswith('.xml'):
                        continue

                    # Extrai o conteúdo do arquivo (após os headers)
                    content_start = part.find(b'\r\n\r\n') + 4
                    content_end = part.rfind(b'\r\n')
                    xml_content = part[content_start:content_end].decode('utf-8')

                    # Processa o XML
                    processador = ProcessadorXMLTISS(xml_content)
                    pacientes = processador.extrair_pacientes()

                    if isinstance(pacientes, dict) and 'error' in pacientes:
                        resultados.append({
                            'arquivo': filename,
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
                        'arquivo': filename,
                        'total_pacientes': len(pacientes),
                        'pacientes': envios_resultado,
                        'mensagem': f'✓ XML processado! {len(pacientes)} guia(s) encontrada(s).'
                    })

                except Exception as e:
                    continue

            if len(resultados) == 0:
                self._send_json_response({
                    'error': 'Nenhum arquivo XML válido foi encontrado'
                }, 400)
                return

            self._send_json_response({
                'success': True,
                'resultados': resultados
            })

        except Exception as e:
            self._send_json_response({
                'error': str(e)
            }, 500)

    def _send_json_response(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

        response = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.wfile.write(response)
