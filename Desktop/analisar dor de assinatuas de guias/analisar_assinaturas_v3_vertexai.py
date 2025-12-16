import os
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = r"C:\Users\Windows 11\Downloads\spry-catcher-449921-h8-bbc989e73ec4 (1).json"
import csv
import boto3
import fitz
import time
import json
import requests
from datetime import datetime, timedelta
from collections import Counter
from PIL import Image
from dotenv import load_dotenv
import mysql.connector
import vertexai
from vertexai.generative_models import GenerativeModel, Part
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException

load_dotenv()

# db configs
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'user': os.getenv('DB_USER', 'root'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

AWS_ACCESS_KEY = os.getenv('AWS_ACCESS_KEY_ID')
AWS_SECRET_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
AWS_REGION = os.getenv('AWS_REGION', 'sa-east-1')
S3_BUCKET_NAME = os.getenv('S3_BUCKET_NAME', 'aplis2')

DIRETORIO_IMAGENS = os.getenv('DIRETORIO_IMAGENS', r'C:\Users\Windows 11\Desktop\imagemAWS')
DIRETORIO_RELATORIOS = os.getenv('DIRETORIO_RELATORIOS', r'C:\Users\Windows 11\Desktop\relatorios_assinaturas')
# Lista de convenios para buscar (STJ, STF, TST, TRT, TRE)
CONVENIOS = [1034, 1035, 1037, 1040, 1041]
TIPO_IMAGEM = int(os.getenv('TIPO_IMAGEM', 16))
LIMITE_REGISTROS = int(os.getenv('LIMITE_REGISTROS', 50))

# login aplis
APLIS_URL = "https://lab.aplis.inf.br/"
APLIS_USER = "api.lab"
APLIS_PASSWORD = "nintendo64"

# Autentique API
AUTENTIQUE_API_URL = "https://api.autentique.com.br/v2/graphql"
AUTENTIQUE_TOKEN = os.getenv('AUTENTIQUE_TOKEN', 'e40ed00a94fb87ae3299bdffeed8cdaddfdaec7ec17efaf981a65c6e77a97ebe')

# Telefones de teste - FORMATOS DIFERENTES!
TELEFONE_WAHA = "556192127911"      # Para WAHA (sem o 9 do celular - 12 dígitos)
TELEFONE_AUTENTIQUE = "5561999356097"  # Para Autentique (com o 9 do celular - 13 dígitos)

# WAHA API
WAHA_URL = "http://localhost:4000"
WAHA_SESSION = "bot-whatsapp"
WAHA_API_KEY = "9bf396abf17140c4abadc2b8846e997a"

# Nomes dos convenios em teste (para mensagens)
CONVENIOS_NOMES = {
    1034: "TST",
    1035: "TRT",
    1037: "TRE",
    1040: "STJ",
    1041: "STF"
}

S3_PREFIXOS = {
    "0040": "lab/Arquivos/Foto/0040/",
    "0085": "lab/Arquivos/Foto/0085/",
    "0100": "lab/Arquivos/Foto/0100/",
    "0101": "lab/Arquivos/Foto/0101/",
    "0200": "lab/Arquivos/Foto/0200/",
    "0031": "lab/Arquivos/Foto/0031/",
    "0102": "lab/Arquivos/Foto/0102/",
    "0103": "lab/Arquivos/Foto/0103/",
    "0300": "lab/Arquivos/Foto/0300/",
    "8511": "lab/Arquivos/Foto/8511/",
    "0032": "lab/Arquivos/Foto/0032/",
    "0049": "lab/Arquivos/Foto/0049/"
}

# Inicializa Vertex AI
print("[INFO] Inicializando Vertex AI (Google Cloud - SEM LIMITE)...")
vertexai.init(project="spry-catcher-449921-h8", location="us-central1")
print("[OK] Vertex AI configurado!")

# GraphQL Mutation para criar documento
CREATE_DOCUMENT_MUTATION = """
mutation CreateDocumentMutation(
  $document: DocumentInput!,
  $signers: [SignerInput!]!,
  $file: Upload!
) {
  createDocument(
    document: $document,
    signers: $signers,
    file: $file
  ) {
    id
    name
    created_at
    signatures {
      public_id
      name
      email
      action { name }
      link { short_link }
    }
  }
}
"""

def enviar_mensagem_waha(telefone, mensagem):
    """Envia mensagem de texto via WAHA WhatsApp"""
    try:
        # Garante formato correto (apenas números)
        telefone_limpo = ''.join(filter(str.isdigit, telefone))

        url = f"{WAHA_URL}/api/sendText"

        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": WAHA_API_KEY
        }

        payload = {
            "session": WAHA_SESSION,
            "chatId": f"{telefone_limpo}@c.us",
            "text": mensagem
        }

        print(f"\n[DEBUG WAHA] Tentando enviar mensagem:")
        print(f"  URL: {url}")
        print(f"  ChatID: {telefone_limpo}@c.us")
        print(f"  Session: {WAHA_SESSION}")
        print(f"  Tamanho da mensagem: {len(mensagem)} caracteres")

        response = requests.post(url, headers=headers, json=payload, timeout=30)

        print(f"  Status HTTP: {response.status_code}")
        if response.text:
            print(f"  Resposta: {response.text[:300]}")

        if response.status_code == 201 or response.status_code == 200:
            print(f"  [OK] Mensagem enviada com sucesso!\n")
            return True
        else:
            print(f"  [ERRO] WAHA retornou status {response.status_code}")
            print(f"  [ERRO] Body: {response.text}\n")
            return False

    except requests.exceptions.ConnectionError as e:
        print(f"  [ERRO] Não foi possível conectar ao WAHA em {WAHA_URL}")
        print(f"  [ERRO] Verifique se o WAHA está rodando: {e}\n")
        return False
    except Exception as e:
        print(f"  [ERRO] Exceção ao enviar mensagem WAHA: {e}")
        import traceback
        traceback.print_exc()
        return False

def aguardar_confirmacao_waha(telefone, timeout=300):
    """Aguarda confirmação do usuário via WhatsApp em tempo real"""
    try:
        telefone_limpo = ''.join(filter(str.isdigit, telefone))
        chat_id = f"{telefone_limpo}@c.us"

        print(f"[INFO] Aguardando resposta no WhatsApp de {telefone}...")
        print(f"[INFO] Responda com 'SIM' ou 'S' para continuar")
        print(f"[INFO] Timeout: {timeout} segundos\n")

        url = f"{WAHA_URL}/api/messages"
        headers = {
            "Content-Type": "application/json",
            "X-Api-Key": WAHA_API_KEY
        }

        inicio = time.time()
        ultima_verificacao = time.time()

        print(f"[DEBUG] Buscando mensagens de: {chat_id}")
        print(f"[DEBUG] Timestamp inicio: {inicio}\n")

        while (time.time() - inicio) < timeout:
            try:
                # Busca mensagens da sessão
                params = {
                    "session": WAHA_SESSION,
                    "chatId": chat_id,
                    "limit": 10
                }

                response = requests.get(url, headers=headers, params=params, timeout=10)

                if response.status_code == 200:
                    mensagens = response.json()

                    print(f"[DEBUG] Total de mensagens recebidas: {len(mensagens)}")

                    # Verifica mensagens recentes
                    for idx, msg in enumerate(mensagens):
                        print(f"[DEBUG] Msg {idx+1}:")
                        print(f"  fromMe: {msg.get('fromMe')}")
                        print(f"  body: {msg.get('body', '')}")
                        print(f"  timestamp: {msg.get('timestamp', 0)}")

                        # Verifica se é mensagem do usuário (fromMe = False)
                        if not msg.get('fromMe', True):
                            texto = msg.get('body', '').strip().upper()
                            timestamp_msg = msg.get('timestamp', 0)

                            print(f"  [DEBUG] Texto em maiúscula: '{texto}'")
                            print(f"  [DEBUG] Comparando timestamp: {timestamp_msg} >= {inicio} = {timestamp_msg >= inicio}")

                            # Mensagem recente (depois do início da espera)
                            if timestamp_msg >= inicio:
                                if texto in ['SIM', 'S', 'YES', 'Y']:
                                    print(f"\n[OK] Confirmação recebida: '{texto}'")
                                    return True
                                elif texto in ['NAO', 'NÃO', 'N', 'NO']:
                                    print(f"\n[INFO] Negativa recebida: '{texto}'")
                                    return False
                            else:
                                print(f"  [DEBUG] Mensagem muito antiga, ignorando")
                        else:
                            print(f"  [DEBUG] Mensagem minha, ignorando")

                    print()  # Linha em branco
                else:
                    print(f"[DEBUG] Status HTTP da API messages: {response.status_code}")
                    print(f"[DEBUG] Resposta: {response.text[:200]}")

                # Aguarda 3 segundos antes da próxima verificação
                time.sleep(3)

                # Mostra status a cada 30 segundos
                if (time.time() - ultima_verificacao) >= 30:
                    tempo_decorrido = int(time.time() - inicio)
                    tempo_restante = timeout - tempo_decorrido
                    print(f"[INFO] Aguardando... ({tempo_restante}s restantes)")
                    ultima_verificacao = time.time()

            except requests.exceptions.Timeout:
                print(f"[AVISO] Timeout na verificação de mensagens")
                time.sleep(5)
                continue
            except Exception as e:
                print(f"[AVISO] Erro ao verificar mensagens: {e}")
                import traceback
                traceback.print_exc()
                time.sleep(5)
                continue

        print(f"[AVISO] Timeout atingido ({timeout}s). Nenhuma confirmação recebida.")
        return False

    except Exception as e:
        print(f"[ERRO] Erro ao aguardar confirmação WAHA: {e}")
        import traceback
        traceback.print_exc()
        return False

def converter_imagem_para_pdf(caminho_imagem):
    """Converte imagem JPG/JPEG/PNG para PDF"""
    try:
        extensao = os.path.splitext(caminho_imagem)[1].upper()

        if extensao not in ['.JPG', '.JPEG', '.PNG']:
            return caminho_imagem  # Já é PDF ou outro formato

        # Cria caminho do PDF temporário
        caminho_pdf = caminho_imagem.rsplit('.', 1)[0] + '_converted.pdf'

        # Abre a imagem e converte para PDF
        img = Image.open(caminho_imagem)

        # Converte para RGB se necessário (PNG com transparência)
        if img.mode in ('RGBA', 'LA', 'P'):
            rgb_img = Image.new('RGB', img.size, (255, 255, 255))
            rgb_img.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = rgb_img

        # Salva como PDF
        img.save(caminho_pdf, 'PDF', resolution=100.0, quality=95)
        print(f"    [OK] Imagem convertida para PDF: {os.path.basename(caminho_pdf)}")

        return caminho_pdf

    except Exception as e:
        print(f"    [ERRO] Falha ao converter imagem para PDF: {e}")
        return None

def enviar_documento_autentique_whatsapp(caminho_arquivo, cod_requisicao, nome_paciente, telefone):
    """Envia documento para assinatura via WhatsApp usando Autentique"""
    arquivo_temp = None
    try:
        if not os.path.exists(caminho_arquivo):
            print(f"    [ERRO] Arquivo não encontrado: {caminho_arquivo}")
            return None

        # Converte imagem para PDF se necessário
        extensao = os.path.splitext(caminho_arquivo)[1].upper()
        if extensao in ['.JPG', '.JPEG', '.PNG']:
            print(f"    [INFO] Detectado arquivo de imagem, convertendo para PDF...")
            caminho_pdf = converter_imagem_para_pdf(caminho_arquivo)
            if not caminho_pdf:
                return None
            arquivo_temp = caminho_pdf  # Marca para deletar depois
        else:
            caminho_pdf = caminho_arquivo

        # Formata telefone para Autentique (precisa do +55)
        telefone_limpo = ''.join(filter(str.isdigit, telefone))

        # Se já tem 55 no início, adiciona +, senão adiciona +55
        if telefone_limpo.startswith('55') and len(telefone_limpo) == 13:
            telefone_autentique = f"+{telefone_limpo}"
        elif len(telefone_limpo) == 11:
            telefone_autentique = f"+55{telefone_limpo}"
        else:
            telefone_autentique = f"+{telefone_limpo}"

        print(f"    [DEBUG] Telefone original: {telefone}")
        print(f"    [DEBUG] Telefone formatado: {telefone_autentique}")
        print(f"    [DEBUG] Nome paciente: {nome_paciente}")
        print(f"    [DEBUG] Arquivo final: {caminho_pdf}")

        nome_documento = f"Requisicao_{cod_requisicao}_Assinatura"

        headers = {"Authorization": f"Bearer {AUTENTIQUE_TOKEN}"}

        variables = {
            "document": {"name": nome_documento},
            "signers": [{
                "name": nome_paciente,
                "phone": telefone_autentique,
                "delivery_method": "DELIVERY_METHOD_WHATSAPP",
                "action": "SIGN"
            }],
            "file": None
        }

        operations = {
            "query": CREATE_DOCUMENT_MUTATION,
            "variables": variables
        }

        file_map = {"0": ["variables.file"]}

        with open(caminho_pdf, 'rb') as pdf_file:
            files = {
                'operations': (None, json.dumps(operations), 'application/json'),
                'map': (None, json.dumps(file_map), 'application/json'),
                '0': (os.path.basename(caminho_pdf), pdf_file, 'application/pdf')
            }

            response = requests.post(
                AUTENTIQUE_API_URL,
                headers=headers,
                files=files,
                timeout=60
            )

            print(f"    [DEBUG] Status HTTP: {response.status_code}")
            print(f"    [DEBUG] Resposta completa: {response.text[:500]}")

            if response.status_code == 200:
                resultado = response.json()

                if 'errors' in resultado:
                    print(f"    [ERRO] Erro na API Autentique:")
                    for erro in resultado['errors']:
                        msg = erro.get('message', 'Erro desconhecido')
                        print(f"      Mensagem: {msg}")

                        # Mostra mais detalhes do erro se houver
                        if 'extensions' in erro:
                            print(f"      Extensions: {erro['extensions']}")
                        if 'path' in erro:
                            print(f"      Path: {erro['path']}")

                        # Mostra o erro completo
                        print(f"      [DEBUG] Erro completo: {json.dumps(erro, indent=2)}")
                    return None

                if 'data' in resultado and 'createDocument' in resultado['data']:
                    doc = resultado['data']['createDocument']
                    print(f"    [OK] Documento enviado! ID: {doc['id']}")
                    print(f"    📱 WhatsApp: {telefone}")

                    # Limpa arquivo temporário se foi criado
                    if arquivo_temp and os.path.exists(arquivo_temp):
                        try:
                            os.remove(arquivo_temp)
                            print(f"    [INFO] Arquivo temporário removido")
                        except:
                            pass

                    return doc

            print(f"    [ERRO] HTTP {response.status_code}: {response.text[:500]}")

            # Limpa arquivo temporário em caso de erro
            if arquivo_temp and os.path.exists(arquivo_temp):
                try:
                    os.remove(arquivo_temp)
                except:
                    pass

            return None

    except Exception as e:
        print(f"    [ERRO] Exceção ao enviar documento: {e}")

        # Limpa arquivo temporário em caso de exceção
        if arquivo_temp and os.path.exists(arquivo_temp):
            try:
                os.remove(arquivo_temp)
            except:
                pass

        return None

def buscar_requisicoes_sem_assinatura(data_inicial, data_final):
    """Busca requisições no banco (AGORA COM TIPO 1 E TIPO 16!)"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)
        print(f"[OK] Conectado ao banco: {DB_CONFIG['database']}")

        # Cria placeholders para a lista de convenios
        convenios_placeholders = ','.join(['%s'] * len(CONVENIOS))

        # Query modificada: busca requisições que TÊM tipo 1 OU tipo 16 MAS NÃO TÊM tipo 15
        # Agrupa por requisição para pegar todas as imagens (tipo 1 e 16) da mesma req
        query = f"""
            SELECT
                r.CodRequisicao,
                r.CodPaciente,
                ri.NomArquivo,
                ri.Tipo,
                r.IdLocalOrigem,
                r.DtaSolicitacao,
                r.IdConvenio
            FROM requisicao r
            INNER JOIN requisicaoimagem ri ON r.IdRequisicao = ri.IdRequisicao
            WHERE ri.Tipo IN (1, 16)
              AND ri.Inativo = 0
              AND r.IdConvenio IN ({convenios_placeholders})
              AND NOT EXISTS (
                  SELECT 1
                  FROM requisicaoimagem ri2
                  WHERE ri2.IdRequisicao = r.IdRequisicao
                    AND ri2.Tipo = 15
                    AND ri2.Inativo = 0
              )
        """

        params = CONVENIOS.copy()

        # Filtra por DtaSolicitacao (DtaImg esta NULL para este tipo)
        if data_inicial and data_final:
            query += " AND DATE(r.DtaSolicitacao) BETWEEN %s AND %s"
            params.extend([data_inicial, data_final])

        query += " ORDER BY r.DtaSolicitacao DESC, r.CodRequisicao, ri.Tipo"
        query += f" LIMIT {LIMITE_REGISTROS * 2}"  # Aumenta limite pois agora pega 2 tipos

        cursor.execute(query, params)
        resultados = cursor.fetchall()

        if not resultados:
            print(f"\n[AVISO] Nenhuma requisicao encontrada para o periodo informado!")
            print(f"[INFO] Verifique se existem requisicoes com Tipo 1 ou 16 e Convenios={CONVENIOS} nesse periodo")

        cursor.close()
        conn.close()

        return resultados

    except mysql.connector.Error as e:
        print(f"[ERRO] Erro MySQL: {e}")
        return []

def buscar_telefones_paciente(cod_paciente):
    """Busca telefones do paciente"""
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT NumTelefone
            FROM telefone
            WHERE Origem = 1 AND CodOrigem = %s
        """

        cursor.execute(query, [cod_paciente])
        resultados = cursor.fetchall()

        cursor.close()
        conn.close()

        # Retorna lista de números
        return [r['NumTelefone'] for r in resultados]

    except mysql.connector.Error as e:
        print(f"[ERRO] Erro ao buscar telefones: {e}")
        return []

def criar_tarefas_aplis_selenium(lista_requisicoes):
    """Cria tarefas no Aplis usando Selenium para pacientes sem telefone"""
    if not lista_requisicoes:
        print("[INFO] Nenhuma tarefa para criar no Aplis")
        return

    print(f"\n{'='*80}")
    print(f"[APLIS] CRIACAO DE TAREFAS VIA SELENIUM")
    print(f"{'='*80}")
    print(f"Total de tarefas a criar: {len(lista_requisicoes)}\n")

    options = webdriver.ChromeOptions()
    options.add_argument('--start-maximized')
    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 30)
    tarefas_criadas = 0

    try:
        # Login no Aplis
        driver.get(APLIS_URL)
        print("[APLIS] Aguardando carregamento do site...")
        time.sleep(5)

        # Clica no botão de aceitar política ANTES do login
        try:
            print("[APLIS] Clicando no botao de politica...")
            btn_politica = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#divLoginPolitica > div > div.btn > input[type=button]")))
            driver.execute_script("arguments[0].click();", btn_politica)
            time.sleep(2)
            print("[OK] Botao de politica clicado")
        except Exception as e:
            print(f"[AVISO] Botao de politica nao encontrado (pode ja ter sido aceito): {e}")

        print("[APLIS] Realizando login...")
        campo_login = wait.until(EC.visibility_of_element_located((By.XPATH, "//*[@id='login']")))
        driver.execute_script("arguments[0].scrollIntoView(true);", campo_login)
        time.sleep(2)
        campo_login.clear()
        campo_login.send_keys(APLIS_USER)
        time.sleep(2)

        campo_senha = wait.until(EC.visibility_of_element_located((By.XPATH, "//*[@id='senha']")))
        campo_senha.clear()
        campo_senha.send_keys(APLIS_PASSWORD)
        time.sleep(2)
        campo_senha.send_keys(Keys.ENTER)
        time.sleep(5)
        print("[OK] Login realizado com sucesso")

        # Fecha popup/modal DEPOIS do login
        try:
            print("[APLIS] Fechando popup pos-login...")
            btn_fechar_popup = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "body > div:nth-child(63) > div.ui-dialog-titlebar.ui-corner-all.ui-widget-header.ui-helper-clearfix.ui-draggable-handle > button")))
            driver.execute_script("arguments[0].click();", btn_fechar_popup)
            time.sleep(2)
            print("[OK] Popup fechado")
        except Exception as e:
            print(f"[AVISO] Popup pos-login nao encontrado: {e}")

        # Navega para area de tarefas
        print("[APLIS] Navegando para area de tarefas...")
        try:
            header = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[@id='divHeader']/div[1]")))
            driver.execute_script("arguments[0].click();", header)
            time.sleep(3)
        except Exception:
            print("[AVISO] Header nao clicado (continuando)")

        area_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//*[@id='divAreas']/ul/li[2]/a")))
        driver.execute_script("arguments[0].scrollIntoView(true);", area_btn)
        time.sleep(2)
        driver.execute_script("arguments[0].click();", area_btn)
        time.sleep(3)

        # Muda para nova aba se abriu
        if len(driver.window_handles) > 1:
            driver.switch_to.window(driver.window_handles[-1])

        time.sleep(5)
        print("[OK] Area de tarefas aberta")

        # Funcao auxiliar para clicar no botao Novo
        def clicar_botao_novo():
            """Tenta abrir modal de nova tarefa"""
            try:
                # Tenta executar funcao cmdNova diretamente
                resultado = driver.execute_script("""
                    if (typeof cmdNova === 'function') {
                        cmdNova();
                        return 'EXECUTADO_CMD_NOVA';
                    }

                    // Tenta encontrar botao visivel com texto "Novo"
                    var botoes = document.querySelectorAll('a, button, div, span');
                    for (var i = 0; i < botoes.length; i++) {
                        var btn = botoes[i];
                        var texto = (btn.textContent || btn.innerText || '').trim().toLowerCase();
                        if (texto === 'novo' && btn.offsetWidth > 0 && btn.offsetHeight > 0) {
                            btn.click();
                            return 'CLICADO_BOTAO_NOVO';
                        }
                    }

                    // Tenta por ID ou classe
                    var btn = document.getElementById('a_nov') ||
                             document.querySelector('.nov') ||
                             document.querySelector('[onclick*="cmdNova"]');
                    if (btn) {
                        btn.click();
                        return 'CLICADO_ID_CLASS';
                    }

                    return 'NAO_ENCONTRADO';
                """)

                if 'CLICADO' in str(resultado) or 'EXECUTADO' in str(resultado):
                    time.sleep(2)
                    try:
                        WebDriverWait(driver, 3).until(
                            EC.presence_of_element_located((By.XPATH, "//*[@id='_taReq']"))
                        )
                        return True
                    except TimeoutException:
                        return False

                return False
            except Exception as e:
                print(f"[ERRO] Erro ao clicar botao Novo: {e}")
                return False

        # Cria tarefas para cada requisicao
        for req_info in lista_requisicoes:
            cod_req = req_info['CodRequisicao']
            cod_paciente = req_info['CodPaciente']
            id_convenio = req_info['IdConvenio']

            print(f"\n[TAREFA] Conv {id_convenio} | Req {cod_req} | Paciente {cod_paciente}")

            # Abre modal de nova tarefa
            if not clicar_botao_novo():
                print("  [ERRO] Nao foi possivel abrir modal. Pulando...")
                continue

            time.sleep(2)

            # Preenche campo requisicao
            try:
                campo_req = wait.until(EC.visibility_of_element_located((By.XPATH, "//*[@id='_taReq']")))
                driver.execute_script("arguments[0].scrollIntoView(true);", campo_req)
                time.sleep(1)
                campo_req.clear()
                campo_req.send_keys(cod_req)
                time.sleep(1)
                print("  [OK] Requisicao preenchida")
            except Exception as e:
                print(f"  [ERRO] Erro ao preencher requisicao: {e}")
                continue

            # Clica no botão de tipo (necessário para habilitar dropdown de setor)
            try:
                print("  [INFO] Clicando no botao de tipo...")
                btn_tipo = driver.find_element(By.CSS_SELECTOR, "#_taTpd2")
                driver.execute_script("arguments[0].scrollIntoView(true);", btn_tipo)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", btn_tipo)
                time.sleep(1)
                print("  [OK] Botao de tipo clicado")
            except Exception as e:
                print(f"  [AVISO] Erro ao clicar botao de tipo: {e}")

            # Seleciona setor "Admissao"
            try:
                resultado = driver.execute_script("""
                    var dropdown = document.getElementById('_taSet');
                    if (dropdown && dropdown.tagName === 'SELECT') {
                        var options = dropdown.options;
                        for (var i = 0; i < options.length; i++) {
                            var texto = options[i].text.toLowerCase();
                            if (texto.includes('admiss')) {
                                dropdown.selectedIndex = i;
                                dropdown.value = options[i].value;
                                dropdown.dispatchEvent(new Event('change', { bubbles: true }));
                                return 'SETOR_SELECIONADO';
                            }
                        }
                    }
                    return 'SETOR_NAO_ENCONTRADO';
                """)

                if 'SELECIONADO' in str(resultado):
                    print("  [OK] Setor 'Admissao' selecionado")
                else:
                    print("  [AVISO] Setor nao selecionado automaticamente")

                time.sleep(1)
            except Exception as e:
                print(f"  [AVISO] Erro ao selecionar setor: {e}")

            # Preenche mensagem
            try:
                nome_convenio = CONVENIOS_NOMES.get(id_convenio, f"Conv {id_convenio}")
                mensagem = f"PACIENTE SEM TELEFONE - Cadastrar telefone da requisição {cod_req} - Convenio {nome_convenio}"

                resultado = driver.execute_script("""
                    var msg = arguments[0];
                    var textarea = document.getElementById('_taMsg') || document.querySelector('textarea');
                    if (textarea) {
                        textarea.value = msg;
                        textarea.dispatchEvent(new Event('input', { bubbles: true }));
                        textarea.dispatchEvent(new Event('change', { bubbles: true }));
                        return 'MENSAGEM_PREENCHIDA';
                    }
                    return 'TEXTAREA_NAO_ENCONTRADO';
                """, mensagem)

                if 'PREENCHIDA' in str(resultado):
                    print("  [OK] Mensagem preenchida")
                else:
                    print("  [AVISO] Mensagem nao preenchida")

                time.sleep(1)
            except Exception as e:
                print(f"  [AVISO] Erro ao preencher mensagem: {e}")

            # Confirma tarefa - USANDO SELETOR ESPECÍFICO
            try:
                print("  [INFO] Tentando clicar no botao de confirmar...")

                # Primeiro tenta pelo seletor CSS específico fornecido
                try:
                    confirm_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
                        "body > div:nth-child(19) > div.ui-dialog-buttonpane.ui-widget-content.ui-helper-clearfix > div > button:nth-child(1) > span.ui-button-icon.ui-icon.ui-icon-check")))
                    driver.execute_script("arguments[0].scrollIntoView(true);", confirm_btn)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", confirm_btn)
                    print("  [OK] Botao clicado via CSS selector especifico")
                except Exception:
                    # Fallback: tenta clicar no botão pai
                    confirm_btn = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR,
                        "body > div:nth-child(19) > div.ui-dialog-buttonpane.ui-widget-content.ui-helper-clearfix > div > button:nth-child(1)")))
                    driver.execute_script("arguments[0].scrollIntoView(true);", confirm_btn)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", confirm_btn)
                    print("  [OK] Botao clicado via CSS selector do botao pai")

                time.sleep(3)
                tarefas_criadas += 1
                print("  [OK] Tarefa criada com sucesso!")

            except Exception as e:
                print(f"  [ERRO] Nao foi possivel confirmar tarefa: {e}")
                print(f"  [INFO] Tentando metodo alternativo...")

                # Método alternativo: busca por texto ou classe
                try:
                    confirm_btn = driver.find_element(By.XPATH,
                        "//button[contains(@class,'btn-primary') or contains(@class,'ui-button') and (contains(.,'Salvar') or contains(.,'Confirmar') or contains(.,'OK'))]")
                    driver.execute_script("arguments[0].scrollIntoView(true);", confirm_btn)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", confirm_btn)
                    time.sleep(3)
                    tarefas_criadas += 1
                    print("  [OK] Tarefa criada com metodo alternativo!")
                except Exception as e2:
                    print(f"  [ERRO] Metodo alternativo falhou: {e2}")
                    # Tenta fechar modal
                    try:
                        close_btn = driver.find_element(By.XPATH,
                            "//button[contains(.,'Cancelar') or contains(.,'Fechar') or contains(@class,'close')]")
                        driver.execute_script("arguments[0].click();", close_btn)
                        time.sleep(0.5)
                    except Exception:
                        pass

        print(f"\n{'='*80}")
        print(f"[RESUMO] Tarefas criadas: {tarefas_criadas}/{len(lista_requisicoes)}")
        print(f"{'='*80}")

        print("\n[APLIS] Navegador permanecera aberto para verificacao...")
        input("Pressione ENTER para fechar o navegador e continuar... ")

    except Exception as e:
        print(f"[ERRO] Erro geral na criacao de tarefas: {e}")
        print("\n[APLIS] Navegador permanecera aberto para debug...")
        input("Pressione ENTER para fechar o navegador... ")
    finally:
        try:
            print("[APLIS] Fechando navegador...")
            driver.quit()
            print("[OK] Navegador fechado!")
        except Exception:
            pass

def criar_cliente_s3():
    """Cria cliente S3"""
    return boto3.client(
        's3',
        aws_access_key_id=AWS_ACCESS_KEY,
        aws_secret_access_key=AWS_SECRET_KEY,
        region_name=AWS_REGION
    )

def baixar_imagem_s3(s3_client, nome_arquivo, cod_requisicao):
    """Baixa imagem do S3"""
    try:
        prefix = next((p for p in S3_PREFIXOS.keys() if cod_requisicao.startswith(p)), None)
        if not prefix:
            return False

        nome_sem_extensao = os.path.splitext(nome_arquivo)[0]
        s3_folder = S3_PREFIXOS[prefix]
        extensoes = ['.jpg', '.jpeg', '.png', '.pdf', '.JPG', '.JPEG', '.PNG', '.PDF']

        for ext in extensoes:
            s3_key = f"{s3_folder}{nome_sem_extensao}{ext}"
            try:
                s3_client.head_object(Bucket=S3_BUCKET_NAME, Key=s3_key)
                extensao_arquivo = os.path.splitext(s3_key)[1]
                caminho_local = os.path.join(DIRETORIO_IMAGENS, f"{nome_sem_extensao}{extensao_arquivo}")

                # SEMPRE baixa, mesmo que ja exista (para garantir dados atualizados)
                s3_client.download_file(S3_BUCKET_NAME, s3_key, caminho_local)
                print(f"    [OK] Baixado: {nome_sem_extensao}{extensao_arquivo}")
                return True
            except:
                continue

        print(f"    [ERRO] Arquivo nao encontrado no S3: {nome_sem_extensao}")
        return False

    except Exception as e:
        print(f"    [ERRO] Erro ao baixar {nome_arquivo}: {e}")
        return False

def baixar_todas_imagens(requisicoes):
    """Baixa todas as imagens via S3"""
    # Limpa diretorio de imagens antes de começar
    if os.path.exists(DIRETORIO_IMAGENS):
        print(f"\n[LIMPEZA] Removendo arquivos antigos de {DIRETORIO_IMAGENS}...")
        arquivos_removidos = 0
        for arquivo in os.listdir(DIRETORIO_IMAGENS):
            caminho_arquivo = os.path.join(DIRETORIO_IMAGENS, arquivo)
            try:
                if os.path.isfile(caminho_arquivo):
                    os.remove(caminho_arquivo)
                    arquivos_removidos += 1
            except Exception as e:
                print(f"    [AVISO] Nao foi possivel remover {arquivo}: {e}")
        print(f"[OK] {arquivos_removidos} arquivo(s) removido(s)")
    else:
        os.makedirs(DIRETORIO_IMAGENS)

    print(f"\n[DOWNLOAD] Conectando a AWS S3...")
    s3_client = criar_cliente_s3()
    print(f"[OK] Conectado ao bucket: {S3_BUCKET_NAME}")
    print(f"[INFO] Total de requisicoes para baixar: {len(requisicoes)}\n")

    total_baixados = 0
    total_ja_existem = 0
    total_erros = 0

    for idx, req in enumerate(requisicoes, 1):
        cod = req['CodRequisicao']
        nome_arquivo = req['NomArquivo']
        id_convenio = req['IdConvenio']
        tipo_img = req.get('Tipo', 'N/A')

        print(f"  [{idx}/{len(requisicoes)}] Conv {id_convenio} | Tipo {tipo_img} | {cod} ({nome_arquivo})")

        arquivos_existentes = [f for f in os.listdir(DIRETORIO_IMAGENS)
                              if f.startswith(os.path.splitext(nome_arquivo)[0])]

        if baixar_imagem_s3(s3_client, nome_arquivo, cod):
            if len(arquivos_existentes) > 0:
                total_baixados += 1
            else:
                total_ja_existem += 1
        else:
            total_erros += 1

    print(f"\n{'='*80}")
    print(f"[INFO] RESUMO DO DOWNLOAD:")
    print(f"   [OK] Baixados agora: {total_baixados}")
    print(f"   [SKIP] Ja existiam: {total_ja_existem}")
    print(f"   [ERRO] Erros: {total_erros}")
    print(f"{'='*80}\n")

    return total_baixados

def converter_pdf_para_imagem(caminho_pdf):
    """Converte PDF para imagem"""
    try:
        doc = fitz.open(caminho_pdf)
        pagina = doc[0]
        matriz = fitz.Matrix(2.0, 2.0)
        pix = pagina.get_pixmap(matrix=matriz)
        caminho_temp = caminho_pdf.replace('.PDF', '_temp.png').replace('.pdf', '_temp.png')
        pix.save(caminho_temp)
        doc.close()
        return caminho_temp
    except Exception as e:
        print(f"    [ERRO] Falha ao converter PDF: {e}")
        return None

def analisar_assinatura_paciente_vertex(caminho_imagem):
    """Analisa imagem com Vertex AI (SEM LIMITE!)"""
    arquivo_temp = None
    try:
        if not os.path.exists(caminho_imagem):
            return None

        # Converte PDF para imagem se necessário
        if caminho_imagem.upper().endswith('.PDF'):
            caminho_temp = converter_pdf_para_imagem(caminho_imagem)
            if not caminho_temp:
                return None
            arquivo_temp = caminho_temp
            caminho_para_analise = caminho_temp
        else:
            caminho_para_analise = caminho_imagem

        # Usa Vertex AI Gemini
        model = GenerativeModel("gemini-2.5-flash")

        with open(caminho_para_analise, 'rb') as f:
            image_data = f.read()

        image_part = Part.from_data(data=image_data, mime_type="image/png" if caminho_para_analise.endswith('.png') else "image/jpeg")

        prompt = """Analise esta imagem e verifique se existe assinatura MANUSCRITA do PACIENTE.

[SUCESSO] PROCURE APENAS:
- Campo "Paciente (Assinatura)" ou "Ass. do Paciente"
- Assinatura na PARTE INFERIOR do documento
- Qualquer marca manuscrita no campo do paciente (assinatura, rubrica, inicial, "X")

[ERRO] IGNORE COMPLETAMENTE:
- Assinatura do médico
- Carimbo médico
- CRM
- Assinaturas na parte superior

Responda apenas: SIM ou NAO"""

        response = model.generate_content([prompt, image_part])
        resposta = response.text.strip().upper()

        tem_assinatura = "SIM" in resposta

        # Limpa arquivo temporário
        if arquivo_temp and os.path.exists(arquivo_temp):
            try:
                os.remove(arquivo_temp)
            except:
                pass

        return tem_assinatura

    except Exception as e:
        print(f"    [ERRO] Erro ao analisar {os.path.basename(caminho_imagem)}: {e}")

        if arquivo_temp and os.path.exists(arquivo_temp):
            try:
                os.remove(arquivo_temp)
            except:
                pass

        return None

def analisar_todas_requisicoes(requisicoes, arquivos_disponiveis):
    """Analisa todas as requisições com Vertex AI (TIPO 1 E TIPO 16!)"""
    resultados = []

    print(f"\n[IA] Analisando {len(requisicoes)} imagens com Vertex AI (Google Cloud)...\n")

    for idx, req in enumerate(requisicoes, 1):
        cod_req = req['CodRequisicao']
        nome_arquivo = req['NomArquivo']
        local_origem = str(req['IdLocalOrigem']) if req['IdLocalOrigem'] else 'Desconhecido'
        id_convenio = req['IdConvenio']
        tipo_img = req.get('Tipo', 'N/A')

        nome_sem_extensao = os.path.splitext(nome_arquivo)[0]
        arquivo_real = arquivos_disponiveis.get(nome_sem_extensao)

        if not arquivo_real:
            for nome in arquivos_disponiveis.values():
                if nome_sem_extensao in nome:
                    arquivo_real = nome
                    break

        if not arquivo_real:
            resultados.append({
                'CodRequisicao': cod_req,
                'TipoImagem': tipo_img,
                'TemAssinatura': 'ARQUIVO_NAO_ENCONTRADO',
                'ArquivoAnalisado': nome_arquivo,
                'LocalOrigem': local_origem,
                'IdConvenio': id_convenio
            })
            print(f"  [{idx}/{len(requisicoes)}] Conv {id_convenio} | Tipo {tipo_img} | {cod_req}: [AVISO] Arquivo nao encontrado")
            continue

        caminho = os.path.join(DIRETORIO_IMAGENS, arquivo_real)
        tem_assinatura = analisar_assinatura_paciente_vertex(caminho)

        emoji = "[OK]" if tem_assinatura else "[ERRO]" if tem_assinatura is not None else "[AVISO]"
        status = "SIM" if tem_assinatura else "NAO" if tem_assinatura is not None else "ERRO"

        print(f"  [{idx}/{len(requisicoes)}] Conv {id_convenio} | Tipo {tipo_img} | {cod_req}: {emoji} {status}")

        resultados.append({
            'CodRequisicao': cod_req,
            'TipoImagem': tipo_img,
            'TemAssinatura': status,
            'ArquivoAnalisado': arquivo_real,
            'LocalOrigem': local_origem,
            'IdConvenio': id_convenio
        })

    return resultados

def gerar_relatorio(resultados):
    """Gera relatório dos resultados"""
    print("\n" + "="*80)
    print("[INFO] RELATORIO DE ANALISE DE ASSINATURAS")
    print("="*80)

    total = len(resultados)
    com_assinatura = sum(1 for r in resultados if r['TemAssinatura'] == 'SIM')
    sem_assinatura = sum(1 for r in resultados if r['TemAssinatura'] == 'NAO')
    nao_encontrado = sum(1 for r in resultados if r['TemAssinatura'] == 'ARQUIVO_NAO_ENCONTRADO')
    erro = sum(1 for r in resultados if r['TemAssinatura'] == 'ERRO')

    print(f"\n RESUMO GERAL:")
    print(f"   Total analisado: {total}")
    print(f"   [OK] COM assinatura: {com_assinatura} ({com_assinatura/total*100:.1f}%)")
    print(f"   [ERRO] SEM assinatura: {sem_assinatura} ({sem_assinatura/total*100:.1f}%)")
    print(f"   [AVISO] Nao encontrado: {nao_encontrado}")
    if erro > 0:
        print(f"    Erros: {erro}")

    if sem_assinatura > 0:
        print(f"\n[ERRO] REQUISICOES SEM ASSINATURA ({sem_assinatura}):")
        sem_assinatura_lista = [r for r in resultados if r['TemAssinatura'] == 'NAO']
        for idx, r in enumerate(sem_assinatura_lista, 1):
            print(f"  {idx:3d}. {r['CodRequisicao']:15s} | Local: {r['LocalOrigem']:10s} | Arquivo: {r['ArquivoAnalisado']}")

        locais = [r['LocalOrigem'] for r in sem_assinatura_lista]
        contagem = Counter(locais)
        print(f"\n ESTATISTICA POR LOCAL:")
        for local, qtd in contagem.most_common():
            print(f"   {local}: {qtd} ({qtd/sem_assinatura*100:.1f}%)")

    if com_assinatura > 0:
        print(f"\n[OK] REQUISICOES COM ASSINATURA ({com_assinatura}):")
        com_assinatura_lista = [r for r in resultados if r['TemAssinatura'] == 'SIM']
        for idx, r in enumerate(com_assinatura_lista, 1):
            print(f"  {idx:3d}. {r['CodRequisicao']:15s} | Local: {r['LocalOrigem']}")

    print("\n" + "="*80)

    return sem_assinatura_lista if sem_assinatura > 0 else []

def salvar_csv(resultados, arquivo):
    """Salva resultados em CSV"""
    if not os.path.exists(DIRETORIO_RELATORIOS):
        os.makedirs(DIRETORIO_RELATORIOS)

    caminho = os.path.join(DIRETORIO_RELATORIOS, arquivo)

    with open(caminho, 'w', newline='', encoding='utf-8') as f:
        campos = ['CodRequisicao', 'IdConvenio', 'TipoImagem', 'TemAssinatura', 'ArquivoAnalisado', 'LocalOrigem']
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(resultados)

    print(f" CSV salvo: {caminho}")

def main():
    print("="*80)
    print("[BUSCA] SISTEMA DE ANALISE DE ASSINATURAS V3 - VERTEX AI")
    print(" Google Cloud (PAGO - SEM LIMITES)")
    print(" Analisa imagens TIPO 1 e TIPO 16")
    print("="*80)

    data_hoje = datetime.now().date()
    data_str = input(f"\nData (DD/MM/YYYY) ou ENTER para hoje [{data_hoje.strftime('%d/%m/%Y')}]: ").strip()

    if data_str:
        try:
            data_final = datetime.strptime(data_str, "%d/%m/%Y").date()
        except ValueError:
            print("[ERRO] Data invalida! Use formato DD/MM/YYYY")
            return
    else:
        data_final = data_hoje

    data_inicial = data_final - timedelta(days=2)
    print(f"[OK] Periodo: {data_inicial.strftime('%d/%m/%Y')} ate {data_final.strftime('%d/%m/%Y')}")

    print(f"\n[INFO] Buscando requisicoes no banco de dados...")
    requisicoes = buscar_requisicoes_sem_assinatura(data_inicial, data_final)

    if not requisicoes:
        print("\n[ERRO] Nenhuma requisicao encontrada no periodo especificado")
        return

    print(f"[OK] Encontradas: {len(requisicoes)} requisicoes")

    total_baixados = baixar_todas_imagens(requisicoes)

    arquivos_disponiveis = {}
    if os.path.exists(DIRETORIO_IMAGENS):
        for arquivo in os.listdir(DIRETORIO_IMAGENS):
            if os.path.isfile(os.path.join(DIRETORIO_IMAGENS, arquivo)):
                nome_base = os.path.splitext(arquivo)[0]
                arquivos_disponiveis[nome_base] = arquivo

    print(f"[OK] Arquivos disponiveis no diretorio: {len(arquivos_disponiveis)}")

    resultados = analisar_todas_requisicoes(requisicoes, arquivos_disponiveis)

    sem_assinatura = gerar_relatorio(resultados)

    # BUSCA TELEFONES DAS REQUISIÇÕES SEM ASSINATURA
    if sem_assinatura:
        print(f"\n{'='*80}")
        print(f"[INFO] BUSCANDO TELEFONES DOS PACIENTES SEM ASSINATURA")
        print(f"{'='*80}\n")

        # Cria dicionários CodRequisicao -> CodPaciente e CodRequisicao -> IdConvenio
        req_paciente_map = {r['CodRequisicao']: r['CodPaciente'] for r in requisicoes}
        req_convenio_map = {r['CodRequisicao']: r['IdConvenio'] for r in requisicoes}

        telefones_encontrados = []
        sem_telefone = []  # Lista para acumular requisições sem telefone

        for req_sem_ass in sem_assinatura:
            cod_req = req_sem_ass['CodRequisicao']
            cod_paciente = req_paciente_map.get(cod_req)
            id_convenio = req_convenio_map.get(cod_req)

            if cod_paciente:
                telefones = buscar_telefones_paciente(cod_paciente)

                if telefones:
                    print(f"[OK] Conv {id_convenio} | Req {cod_req} | Paciente {cod_paciente} | Telefones: {', '.join(telefones)}")
                    telefones_encontrados.append({
                        'CodRequisicao': cod_req,
                        'IdConvenio': id_convenio,
                        'CodPaciente': cod_paciente,
                        'Telefones': ', '.join(telefones),
                        'LocalOrigem': req_sem_ass['LocalOrigem']
                    })
                else:
                    print(f"[AVISO] Conv {id_convenio} | Req {cod_req} | Paciente {cod_paciente} | SEM TELEFONE cadastrado")
                    # Adiciona a lista para criar tarefa depois
                    sem_telefone.append({
                        'CodRequisicao': cod_req,
                        'CodPaciente': cod_paciente,
                        'IdConvenio': id_convenio
                    })
            else:
                print(f"[ERRO] Conv {id_convenio} | Req {cod_req} | SEM CodPaciente")

        # Cria tarefas no Aplis para pacientes sem telefone
        if sem_telefone:
            print(f"\n{'='*80}")
            print(f"[INFO] PACIENTES SEM TELEFONE CADASTRADO")
            print(f"{'='*80}")
            print(f"Total: {len(sem_telefone)} paciente(s)\n")

            for req in sem_telefone:
                print(f"  Conv {req['IdConvenio']} | Req {req['CodRequisicao']} | Paciente {req['CodPaciente']}")

            resposta = input(f"\nDeseja criar tarefas no Aplis para estes pacientes? (S/N): ").strip().upper()

            if resposta == 'S' or resposta == 'SIM':
                criar_tarefas_aplis_selenium(sem_telefone)
            else:
                print("[INFO] Criacao de tarefas cancelada pelo usuario")

        # Salva CSV com telefones
        if telefones_encontrados:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            arquivo_telefones = f"telefones_sem_assinatura_{timestamp}.csv"

            if not os.path.exists(DIRETORIO_RELATORIOS):
                os.makedirs(DIRETORIO_RELATORIOS)

            caminho = os.path.join(DIRETORIO_RELATORIOS, arquivo_telefones)

            with open(caminho, 'w', newline='', encoding='utf-8') as f:
                campos = ['CodRequisicao', 'IdConvenio', 'CodPaciente', 'Telefones', 'LocalOrigem']
                writer = csv.DictWriter(f, fieldnames=campos)
                writer.writeheader()
                writer.writerows(telefones_encontrados)

            print(f"\n[OK] CSV com telefones salvo: {caminho}")
            print(f"Total de pacientes com telefone: {len(telefones_encontrados)}")

        # ENVIO DE DOCUMENTOS VIA AUTENTIQUE (TESTE)
        if sem_assinatura:
            print(f"\n{'='*80}")
            print(f"[AUTENTIQUE] ENVIO DE DOCUMENTOS PARA ASSINATURA VIA WHATSAPP")
            print(f"{'='*80}")
            print(f"Telefone WAHA (notificacoes): {TELEFONE_WAHA}")
            print(f"Telefone Autentique (assinaturas): {TELEFONE_AUTENTIQUE}")
            print(f"Total de requisicoes sem assinatura: {len(sem_assinatura)}\n")

            # Envia mensagem pedindo confirmação via WAHA
            print(f"\n[WAHA] Enviando mensagem de confirmacao no WhatsApp...")
            mensagem_confirmacao = f"""🤖 *Sistema de Análise de Assinaturas*

📊 *Resumo do Processo:*
• {len(sem_assinatura)} requisições SEM assinatura detectadas
• Documentos prontos para envio ao Autentique
• Links de assinatura serão enviados para: +{TELEFONE_AUTENTIQUE}

❓ *Deseja continuar?*
Digite *SIM* para confirmar o envio dos documentos.

⏳ Aguardando sua confirmação..."""

            enviar_mensagem_waha(TELEFONE_WAHA, mensagem_confirmacao)

            # Aguarda confirmação em tempo real via WAHA (300 segundos = 5 minutos)
            confirmacao = aguardar_confirmacao_waha(TELEFONE_WAHA, timeout=300)

            if confirmacao:
                # Envia mensagem de início do processo
                print(f"\n[WAHA] Enviando confirmacao de inicio...")
                mensagem_inicio = f"""✅ *Confirmação Recebida!*

🚀 Iniciando envio dos documentos...

📊 *Detalhes:*
• {len(sem_assinatura)} documentos serão processados
• Você receberá notificações a cada envio
• Links do Autentique chegarão automaticamente no +{TELEFONE_AUTENTIQUE}

⏳ Processando..."""
                enviar_mensagem_waha(TELEFONE_WAHA, mensagem_inicio)

                documentos_enviados = []

                for idx, req_sem_ass in enumerate(sem_assinatura, 1):
                    cod_req = req_sem_ass['CodRequisicao']
                    arquivo = req_sem_ass.get('ArquivoAnalisado', '')
                    cod_paciente = req_paciente_map.get(cod_req, 'Paciente')
                    id_convenio = req_convenio_map.get(cod_req)

                    print(f"\n[{idx}/{len(sem_assinatura)}] Req {cod_req} | Conv {id_convenio} | Paciente {cod_paciente}")

                    # Caminho do arquivo analisado
                    caminho_arquivo = os.path.join(DIRETORIO_IMAGENS, arquivo) if arquivo else None

                    if caminho_arquivo and os.path.exists(caminho_arquivo):
                        doc = enviar_documento_autentique_whatsapp(
                            caminho_arquivo=caminho_arquivo,
                            cod_requisicao=cod_req,
                            nome_paciente=f"Paciente {cod_paciente}",
                            telefone=TELEFONE_AUTENTIQUE
                        )

                        if doc:
                            documentos_enviados.append({
                                'CodRequisicao': cod_req,
                                'IdConvenio': id_convenio,
                                'DocumentoID': doc['id'],
                                'Telefone': TELEFONE_AUTENTIQUE
                            })

                            # Envia notificação por WhatsApp via WAHA
                            nome_convenio = CONVENIOS_NOMES.get(id_convenio, f"Conv {id_convenio}")
                            mensagem_doc = f"""📄 *Documento Enviado [{idx}/{len(sem_assinatura)}]*

✅ Requisição: {cod_req}
🏛️ Convênio: {nome_convenio}
👤 Paciente: {cod_paciente}
🆔 Doc ID: {doc['id']}

O link de assinatura foi enviado pelo Autentique para +{TELEFONE_AUTENTIQUE}!"""
                            enviar_mensagem_waha(TELEFONE_WAHA, mensagem_doc)

                            time.sleep(2)  # Delay entre envios
                    else:
                        print(f"    [AVISO] Arquivo nao encontrado para envio")

                # Salva CSV com documentos enviados
                if documentos_enviados:
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    arquivo_docs = f"documentos_autentique_{timestamp}.csv"

                    caminho = os.path.join(DIRETORIO_RELATORIOS, arquivo_docs)

                    with open(caminho, 'w', newline='', encoding='utf-8') as f:
                        campos = ['CodRequisicao', 'IdConvenio', 'DocumentoID', 'Telefone']
                        writer = csv.DictWriter(f, fieldnames=campos)
                        writer.writeheader()
                        writer.writerows(documentos_enviados)

                    print(f"\n[OK] CSV com documentos enviados salvo: {caminho}")
                    print(f"Total de documentos enviados: {len(documentos_enviados)}")

                    # Mensagem final via WAHA
                    mensagem_final = f"""✅ *Processo Concluído!*

📊 *Resultados Finais:*
✅ {len(documentos_enviados)} documentos enviados com sucesso
📱 Todos os links foram enviados pelo Autentique para +{TELEFONE_AUTENTIQUE}
📋 Relatório CSV gerado

🔔 *Próximos Passos:*
1. Verifique as mensagens do Autentique no WhatsApp
2. Clique nos links para assinar os documentos
3. Confirme as assinaturas

Obrigado por usar o sistema! 🤖"""
                    enviar_mensagem_waha(TELEFONE_WAHA, mensagem_final)
            else:
                print("[INFO] Envio de documentos cancelado pelo usuario")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    salvar_csv(resultados, f"analise_assinaturas_{timestamp}.csv")

    print("\n[OK] Processo concluido!")

if __name__ == "__main__":
    main()