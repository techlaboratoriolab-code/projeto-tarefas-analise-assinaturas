import os
import base64
import requests
from xml.etree import ElementTree as ET
from pathlib import Path
import hashlib
import re
from datetime import datetime
import time

class OrizonTISSEnvio:
    def __init__(self, codigo_prestador, login, senha, registro_ans="005711"):
        """
        Inicializa o cliente de envio TISS Orizon

        Args:
            codigo_prestador: Código do prestador na operadora
            login: Login do prestador
            senha: Senha do prestador (pode ser texto puro ou já em MD5)
            registro_ans: Registro ANS da operadora (padrão: 005711)
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
    
    def pdf_para_base64(self, caminho_pdf):
        """
        Converte PDF para base64
        """
        if not os.path.exists(caminho_pdf):
            raise FileNotFoundError(f"PDF não encontrado: {caminho_pdf}")
        
        with open(caminho_pdf, 'rb') as pdf_file:
            pdf_content = pdf_file.read()
            pdf_base64 = base64.b64encode(pdf_content).decode('utf-8')
        
        return pdf_base64
    
    def enviar_documento(self, numero_lote, numero_protocolo, numero_guia_prestador,
                        numero_guia_operadora, numero_documento, caminho_pdf,
                        natureza_guia="2", tipo_documento="01", observacao="", max_tentativas=3):
        """
        Envia um documento para o webservice TISS Orizon com retry automático
        """
        # Converte PDF para base64
        try:
            pdf_base64 = self.pdf_para_base64(caminho_pdf)
            tamanho_kb = len(pdf_base64) / 1024
        except Exception as e:
            return {
                'success': False,
                'error': f"Erro ao converter PDF: {str(e)}"
            }

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
                    print(f"   🔄 Tentativa {tentativa}/{max_tentativas}...")
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
    
    def __init__(self, caminho_xml, pasta_pdfs):
        self.caminho_xml = caminho_xml
        self.pasta_pdfs = pasta_pdfs
        self.pacientes = []
        
    def extrair_pacientes(self):
        """
        Extrai dados dos pacientes do XML TISS (lote de guias)
        """
        print("\n🔍 Analisando XML TISS (Lote de Guias)...")
        
        if not os.path.exists(self.caminho_xml):
            print(f"❌ ERRO: Arquivo não encontrado: {self.caminho_xml}")
            return []
        
        print(f"   ✓ Arquivo encontrado: {os.path.basename(self.caminho_xml)}")
        
        # Lê o XML
        tree = ET.parse(self.caminho_xml)
        root = tree.getroot()
        
        # Extrai o número do lote
        numero_lote = self._extrair_texto(root, './/numeroLote', 'Número do lote')
        
        print(f"   📦 Lote: {numero_lote}")
        
        # Busca por todos os tipos de guias possíveis no padrão TISS
        tipos_guias = [
            'guiaConsulta',
            'guiaSP-SADT', 
            'guiaSADT',
            'guiaResumoInternacao',
            'guiaHonorarioIndividual',
            'guiaTratamentoOdontologico',
            'guiaOdontologia',
            'guiaInternacao'
        ]
        
        guias_encontradas = []
        
        for tipo_guia in tipos_guias:
            for elem in root.iter():
                if tipo_guia.lower() in elem.tag.lower():
                    guias_encontradas.append(elem)
        
        print(f"   ✓ Encontradas {len(guias_encontradas)} guia(s)")
        
        if not guias_encontradas:
            return []
        
        # Processa cada guia
        for i, guia in enumerate(guias_encontradas, 1):
            paciente = self._extrair_dados_guia(guia, numero_lote)
            
            if paciente:
                self.pacientes.append(paciente)
        
        print(f"   ✅ Total: {len(self.pacientes)} paciente(s) extraído(s)")
        
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
    
    def buscar_pdf_paciente(self, paciente):
        """
        Busca o PDF do paciente pelo número da guia
        Formato esperado: NUMERODAGUIA_GUIA_doc1.pdf
        """
        if not os.path.exists(self.pasta_pdfs):
            return None
        
        guia = paciente.get('numeroGuiaPrestador', '')
        
        if not guia:
            return None
        
        # Busca pelo padrão: 357174867_GUIA_doc1.pdf
        pdf_esperado = os.path.join(self.pasta_pdfs, f"{guia}_GUIA_doc1.pdf")
        
        if os.path.exists(pdf_esperado):
            return pdf_esperado
        
        # Busca alternativa: apenas o número da guia
        pdfs = list(Path(self.pasta_pdfs).glob('*.pdf'))
        for pdf in pdfs:
            if guia in pdf.stem:
                return str(pdf)
        
        return None
    
    def processar_envios(self, cliente_orizon, intervalo_segundos=2):
        """
        Processa o envio de todos os pacientes
        """
        if not self.pacientes:
            self.extrair_pacientes()
        
        if not self.pacientes:
            print("\n❌ ERRO: Nenhum paciente encontrado no XML!")
            return []
        
        resultados = []
        
        print("\n" + "="*80)
        print("🚀 PROCESSANDO ENVIOS")
        print("="*80)
        
        total = len(self.pacientes)
        
        for i, paciente in enumerate(self.pacientes, 1):
            print(f"\n[{i}/{total}] {'='*60}")
            print(f"💳 Carteirinha: {paciente.get('carteirinha', 'N/A')}")
            print(f"🏥 Guia: {paciente.get('numeroGuiaPrestador', 'N/A')}")
            
            # Busca o PDF
            caminho_pdf = self.buscar_pdf_paciente(paciente)
            
            if not caminho_pdf:
                print(f"   ❌ PDF não encontrado")
                resultados.append({
                    'paciente': paciente,
                    'status': 'PDF não encontrado',
                    'success': False
                })
                continue
            
            print(f"   📄 PDF: {os.path.basename(caminho_pdf)}")
            print(f"   📤 Enviando...")
            
            # Realiza o envio
            resultado = cliente_orizon.enviar_documento(
                numero_lote=paciente.get('numeroLote', ''),
                numero_protocolo=paciente.get('numeroProtocolo', ''),
                numero_guia_prestador=paciente.get('numeroGuiaPrestador', ''),
                numero_guia_operadora=paciente.get('numeroGuiaOperadora', ''),
                numero_documento=paciente.get('numeroDocumento', ''),
                caminho_pdf=caminho_pdf,
                natureza_guia='2',
                tipo_documento='01',
                observacao=''
            )

            if resultado['success']:
                tentativas = resultado.get('tentativas', 1)
                if tentativas > 1:
                    print(f"   ✅ SUCESSO (após {tentativas} tentativas)!")
                else:
                    print(f"   ✅ SUCESSO!")
            else:
                print(f"   ❌ ERRO: {resultado.get('error', 'Erro desconhecido')}")
            
            resultados.append({
                'paciente': paciente,
                'status': 'Enviado' if resultado['success'] else 'Erro',
                'success': resultado['success'],
                'pdf': caminho_pdf,
                'resposta': resultado
            })
            
            # Aguarda entre envios para não sobrecarregar
            if i < total:
                time.sleep(intervalo_segundos)
        
        return resultados
    
    def gerar_relatorio(self, resultados, arquivo_saida='relatorio_envios.txt'):
        """
        Gera relatório dos envios
        """
        with open(arquivo_saida, 'w', encoding='utf-8') as f:
            f.write("="*80 + "\n")
            f.write("RELATÓRIO DE ENVIOS TISS - ORIZON\n")
            f.write("="*80 + "\n\n")
            
            sucessos = sum(1 for r in resultados if r['success'])
            falhas = len(resultados) - sucessos
            
            f.write(f"Total de envios: {len(resultados)}\n")
            f.write(f"Sucessos: {sucessos}\n")
            f.write(f"Falhas: {falhas}\n")
            if len(resultados) > 0:
                f.write(f"Taxa de sucesso: {(sucessos/len(resultados)*100):.1f}%\n\n")
            
            f.write("="*80 + "\n")
            f.write("DETALHAMENTO\n")
            f.write("="*80 + "\n\n")
            
            for i, res in enumerate(resultados, 1):
                pac = res['paciente']
                f.write(f"[{i}] {'✓' if res['success'] else '✗'}\n")
                f.write(f"    Carteirinha: {pac.get('carteirinha', 'N/A')}\n")
                f.write(f"    Guia Prestador: {pac.get('numeroGuiaPrestador', 'N/A')}\n")
                f.write(f"    PDF: {os.path.basename(res.get('pdf', 'N/A'))}\n")
                f.write(f"    Status: {res['status']}\n")
                
                if not res['success'] and 'resposta' in res:
                    f.write(f"    Erro: {res['resposta'].get('error', 'N/A')}\n")
                
                f.write("\n")
        
        print(f"\n📊 Relatório salvo em: {arquivo_saida}")


# ==============================================================================
# SCRIPT PRINCIPAL
# ==============================================================================

if __name__ == "__main__":
    
    print("="*80)
    print("🏥 SISTEMA DE ENVIO AUTOMÁTICO DE DOCUMENTOS TISS - ORIZON")
    print("="*80)
    
    # ==================================================================
    # CONFIGURAÇÕES
    # ==================================================================
    
    CAMINHO_XML = r"C:\Users\Windows 11\Desktop\anexo de imagens via web service orizon\identificação via xml de pacientes\4304_001.XML"
    PASTA_PDFS = r"C:\Users\Windows 11\Desktop\anexo de imagens via web service orizon\guias envio"
    
    # Credenciais Orizon
    CODIGO_PRESTADOR = "0000263036"  
    LOGIN = "LAB0186"                 
    SENHA = "91a2ab8fbdd7884f7e32fd19694712a0"         # ⚠️ PREENCHA SUA SENHA AQUI
    REGISTRO_ANS = "005711"
    
    # Intervalo entre envios (segundos)
    INTERVALO_ENVIOS = 2
    
    # ==================================================================
    # ANÁLISE DO XML
    # ==================================================================
    
    print("\n" + "="*80)
    print("📋 ANALISANDO XML E PDFS")
    print("="*80)
    
    processador = ProcessadorXMLTISS(CAMINHO_XML, PASTA_PDFS)
    pacientes = processador.extrair_pacientes()
    
    if not pacientes:
        print("\n❌ Nenhum paciente encontrado no XML!")
        exit()
    
    # Verifica quantos PDFs estão disponíveis
    pdfs_encontrados = 0
    pdfs_faltando = []
    
    for pac in pacientes:
        pdf = processador.buscar_pdf_paciente(pac)
        if pdf:
            pdfs_encontrados += 1
        else:
            pdfs_faltando.append(pac.get('numeroGuiaPrestador', 'N/A'))
    
    print(f"\n📊 RESUMO:")
    print(f"   Total de pacientes: {len(pacientes)}")
    print(f"   PDFs encontrados: {pdfs_encontrados}")
    print(f"   PDFs faltando: {len(pdfs_faltando)}")
    
    if pdfs_faltando:
        print(f"\n⚠️  Guias sem PDF:")
        for guia in pdfs_faltando[:10]:  # Mostra apenas os 10 primeiros
            print(f"      - {guia}")
        if len(pdfs_faltando) > 10:
            print(f"      ... e mais {len(pdfs_faltando) - 10}")
    
    if pdfs_encontrados == 0:
        print("\n❌ Nenhum PDF encontrado! Verifique o nome dos arquivos.")
        print("   Formato esperado: NUMERODAGUIA_GUIA_doc1.pdf")
        print("   Exemplo: 357174867_GUIA_doc1.pdf")
        exit()
    
    # ==================================================================
    # CONFIRMAÇÃO E ENVIO
    # ==================================================================
    
    print("\n" + "="*80)
    print("🚀 ENVIO EM PRODUÇÃO")
    print("="*80)
    
    print(f"\n⚠️  ATENÇÃO:")
    print(f"   - Serão enviados {pdfs_encontrados} documento(s)")
    print(f"   - Intervalo entre envios: {INTERVALO_ENVIOS}s")
    print(f"   - Tempo estimado: ~{(pdfs_encontrados * INTERVALO_ENVIOS / 60):.1f} minutos")
    
    resposta = input("\n❓ Confirma o envio? Digite 'SIM' em maiúsculas: ")
    
    if resposta == 'SIM':
        print("\n🚀 Iniciando envios...")
        print("="*80)
        
        cliente = OrizonTISSEnvio(CODIGO_PRESTADOR, LOGIN, SENHA, REGISTRO_ANS)
        resultados = processador.processar_envios(cliente, INTERVALO_ENVIOS)
        
        processador.gerar_relatorio(resultados, 'relatorio_envio_completo.txt')
        
        # Resumo final
        sucessos = sum(1 for r in resultados if r['success'])
        falhas = len(resultados) - sucessos
        
        print("\n" + "="*80)
        print("✅ PROCESSO FINALIZADO!")
        print("="*80)
        print(f"📊 Total processado: {len(resultados)}")
        print(f"✅ Sucessos: {sucessos}")
        print(f"❌ Falhas: {falhas}")
        if len(resultados) > 0:
            print(f"📈 Taxa de sucesso: {(sucessos/len(resultados)*100):.1f}%")
        
        print(f"\n📄 Relatório completo: relatorio_envio_completo.txt")
        
    else:
        print("\n❌ Envio cancelado pelo usuário")