import requests
import json
import csv
import os
from datetime import datetime, time

# --- CONFIGURAÇÕES ---
WAHA_API_URL = "http://localhost:4000"
WAHA_API_KEY = "43092119c8b54d82ae07a0d6941253ee"  # Adicione aqui se necessário (deixe vazio se não usar)
SESSION_NAME = "Backup_atendimento"
MEU_NOME = "Eu (ATENDIMENTO)"

# Usamos 'r' antes da string para que o Python leia o caminho do Windows corretamente.
# Pasta de saída apenas para o arquivo CSV de histórico.
PASTA_SAIDA = r"G:\Meu Drive\Histórico WhatsApp\historicos_diarios"

# PASTA_MIDIA e a lógica de mídia foram removidas.
LIMITE_BUSCA_CHATS = 1000
LIMITE_MENSAGENS_POR_CHAT = 250
# ----------------------------------------------------

# ==============================================================================
# CLASSE DE CONEXÃO E AUTENTICAÇÃO WAHA
# ==============================================================================
class WAHAConnector:
    def __init__(self, waha_url: str, session: str = "default", api_key: str = ""):
        """
        Inicializa a conexão com WAHA
        """
        self.waha_url = waha_url.rstrip('/')
        self.session = session
        self.headers = {'Content-Type': 'application/json'}

        # Adiciona API Key nos headers se fornecida
        if api_key:
            self.headers['X-Api-Key'] = api_key

    def test_connection(self) -> bool:
        """Testa conexão com WAHA"""
        try:
            response = requests.get(
                f"{self.waha_url}/api/version",
                headers=self.headers,
                timeout=10
            )
            if response.status_code == 200:
                version_info = response.json()
                print(f"✓ Conectado ao WAHA {version_info.get('version', 'N/A')}")
                return True
            else:
                print(f"✗ Erro na conexão: status {response.status_code}")
                if response.status_code == 401:
                    print("   -> 🚨 Autenticação Falhou (401). Verifique a WAHA_API_KEY.")
                return False
        except Exception as e:
            print(f"✗ Erro de conexão: {e}")
            return False

    def test_session(self) -> bool:
        """Verifica se a sessão está ativa"""
        try:
            response = requests.get(
                f"{self.waha_url}/api/sessions",
                headers=self.headers,
                timeout=10
            )
            if response.status_code == 200:
                sessions = response.json()
                found = False
                for session in sessions:
                    if session.get('name') == self.session:
                        found = True
                        status = session.get('status', 'UNKNOWN')
                        if status == 'WORKING':
                            print(f"✓ Sessão '{self.session}' está ativa e conectada")
                            return True
                        else:
                            print(f"✗ Sessão '{self.session}' com status: {status}")
                            print("   -> Por favor, escaneie o QR Code no WAHA")
                            return False
                if not found:
                    print(f"✗ Sessão '{self.session}' não encontrada")
                    print("   -> Verifique se o nome da sessão está correto")
                return False
            else:
                print(f"✗ Erro ao verificar sessões: status {response.status_code}")
                return False
        except Exception as e:
            print(f"✗ Erro ao verificar sessão: {e}")
            return False

    def verify_authentication(self) -> bool:
        """
        Executa verificação completa de autenticação
        Retorna True se tudo estiver OK
        """
        print("\n" + "="*60)
        print("VERIFICANDO AUTENTICAÇÃO E CONEXÃO COM WAHA")
        print("="*60)

        # Testa conexão básica
        if not self.test_connection():
            print("\n❌ Falha na conexão com WAHA")
            print("   -> Verifique se o WAHA está rodando")
            print(f"   -> URL configurada: {self.waha_url}")
            return False

        # Testa sessão do WhatsApp
        if not self.test_session():
            print("\n❌ Sessão do WhatsApp não está ativa")
            print(f"   -> Sessão configurada: {self.session}")
            print("   -> Acesse o WAHA e escaneie o QR Code")
            return False

        print("\n✅ Autenticação verificada com sucesso!")
        print("="*60)
        return True

# A função 'baixar_midia' foi removida, pois você não a quer.
# A função 'get_active_chats_for_date' permanece inalterada, pois apenas busca os chats.

def get_active_chats_for_date(target_date, headers):
    """Busca todos os chats e retorna os que tiveram atividade na data especificada."""
    print(f"\nBuscando conversas ativas para o dia {target_date.strftime('%d/%m/%Y')}...")
    endpoint = f"{WAHA_API_URL}/api/{SESSION_NAME}/chats/overview"
    params = {"limit": LIMITE_BUSCA_CHATS}
    active_chats = []
    try:
        response = requests.get(endpoint, params=params, headers=headers, timeout=120)
        response.raise_for_status()
        all_chats = response.json()
        start_of_day = datetime.combine(target_date, time.min)
        end_of_day = datetime.combine(target_date, time.max)
        for chat in all_chats:
            last_message = chat.get('lastMessage')
            if last_message and last_message.get('timestamp'):
                # Converte o timestamp para datetime
                last_msg_ts = datetime.fromtimestamp(int(last_message['timestamp']))
                # Verifica se a última mensagem ocorreu no dia alvo
                if start_of_day <= last_msg_ts <= end_of_day:
                    active_chats.append(chat['id'])
        print(f"-> Encontradas {len(active_chats)} conversas ativas.")
        return active_chats
    except requests.exceptions.RequestException as e:
        print(f"❌ Erro ao buscar a lista de conversas: {e}")
        return []

def fetch_and_write_messages(chat_id, target_date, csv_writer, headers):
    """Baixa o histórico e escreve APENAS as mensagens de texto no CSV."""
    print(f"  - Processando chat: {chat_id}")
    endpoint = f"{WAHA_API_URL}/api/{SESSION_NAME}/chats/{chat_id}/messages"
    # Aumentar o limite pode ser necessário se houver mais de 250 mensagens no dia
    params = {"limit": LIMITE_MENSAGENS_POR_CHAT}
    try:
        response = requests.get(endpoint, params=params, headers=headers, timeout=120)
        response.raise_for_status()
        all_messages = response.json()
        
        messages_for_day = []
        start_of_day = datetime.combine(target_date, time.min)
        end_of_day = datetime.combine(target_date, time.max)

        for msg in all_messages:
            msg_ts_value = msg.get('timestamp')
            if msg_ts_value:
                msg_ts = datetime.fromtimestamp(int(msg_ts_value))
                # Filtra apenas as mensagens dentro do dia alvo
                if start_of_day <= msg_ts <= end_of_day:
                    messages_for_day.append(msg)
        
        if not messages_for_day:
            print(f"    -> Nenhuma mensagem encontrada neste dia para {chat_id}.")
            return
        
        # Ordena as mensagens por timestamp
        messages_for_day.sort(key=lambda m: m.get('timestamp'))
        
        for msg in messages_for_day:
            remetente = MEU_NOME if msg.get('fromMe') else msg.get('from', 'Desconhecido')
            
            corpo = ""
            if msg.get('hasMedia'):
                # LÓGICA ALTERADA: Apenas registra a mídia
                if msg.get('caption'):
                    corpo = f"[MÍDIA] | Legenda: {msg.get('caption')}"
                else:
                    corpo = "[MÍDIA]"
            else:
                # Usa o corpo da mensagem ou uma tag se não houver texto
                corpo = msg.get('body', '[Mensagem sem texto]')

            data_hora = datetime.fromtimestamp(int(msg.get('timestamp'))).strftime('%d/%m/%Y %H:%M:%S')
            # Limpa quebras de linha no conteúdo para o CSV
            corpo_limpo = corpo.replace('\n', ' ').replace('\r', '')
            
            # Escreve a linha no arquivo CSV
            csv_writer.writerow([chat_id, data_hora, remetente, corpo_limpo])
            
        print(f"    -> {len(messages_for_day)} mensagens de '{chat_id}' adicionadas ao arquivo.")

    except requests.exceptions.RequestException as e:
        print(f"    -> ❌ Erro ao baixar o histórico para {chat_id}: {e}")

if __name__ == "__main__":
    print("="*70)
    print("FERRAMENTA DE DOWNLOAD DE HISTÓRICOS DIÁRIOS - SOMENTE TEXTO")
    print("="*70)

    # Inicializa o conector WAHA
    connector = WAHAConnector(WAHA_API_URL, SESSION_NAME, WAHA_API_KEY)

    # Verifica autenticação antes de prosseguir
    if not connector.verify_authentication():
        print("\n❌ Não foi possível continuar sem autenticação válida.")
        print("   Verifique as configurações e tente novamente.")
        exit(1)

    print("\n" + "="*70)
    date_str = input("Digite a data para a busca (formato DD/MM/AAAA): ")
    try:
        target_date = datetime.strptime(date_str, "%d/%m/%Y")
    except ValueError:
        print("❌ Formato de data inválido. Use DD/MM/AAAA.")
        exit(1)

    active_chat_ids = get_active_chats_for_date(target_date, connector.headers)

    if active_chat_ids:
        print("\nIniciando a coleta e salvamento do histórico de texto no Google Drive...")
        # Garante que a pasta de destino exista
        if not os.path.exists(PASTA_SAIDA):
            print(f"AVISO: A pasta '{PASTA_SAIDA}' não foi encontrada. Criando a pasta...")
            os.makedirs(PASTA_SAIDA)

        output_filename = os.path.join(PASTA_SAIDA, f"historico_{target_date.strftime('%Y-%m-%d')}_somente_texto.csv")

        # Abre o arquivo CSV para escrita
        with open(output_filename, 'w', newline='', encoding='utf-8') as f_csv:
            writer = csv.writer(f_csv, delimiter=';')
            writer.writerow(['ChatID', 'Timestamp', 'Remetente', 'Conteudo'])
            for chat_id in active_chat_ids:
                fetch_and_write_messages(chat_id, target_date, writer, connector.headers)
        
        print(f"\n{'='*70}")
        print("✅ PROCESSO FINALIZADO COM SUCESSO!")
        print(f"{'='*70}")
        print(f"📁 Arquivo salvo em: {output_filename}")
        print("☁️  O Google Drive irá sincronizar o arquivo automaticamente.")
        print(f"{'='*70}")
    else:
        print("\n❌ Nenhuma conversa com atividade na data especificada para baixar.")