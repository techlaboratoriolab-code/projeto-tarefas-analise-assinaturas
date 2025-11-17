# LAB - Sistema de Envio Automático TISS Orizon

Sistema para envio automático de documentos TISS para a operadora Orizon via webservice.

## 🚀 Deploy no Vercel

### Pré-requisitos
- Conta no [Vercel](https://vercel.com)
- Conta no GitHub
- Repositório já configurado

### Passo a Passo para Deploy

1. **Acesse o Vercel**
   - Entre em: https://vercel.com
   - Faça login com sua conta do GitHub

2. **Importe o Projeto**
   - Clique em "Add New..." → "Project"
   - Selecione seu repositório: `projeto-automa-o-web-service`
   - Clique em "Import"

3. **Configure o Projeto**
   - **Framework Preset:** Other
   - **Root Directory:** (deixe vazio ou aponte para a pasta raiz)
   - **Build Command:** (deixe vazio)
   - **Output Directory:** (deixe vazio)

4. **Variáveis de Ambiente** (opcional)
   - Por enquanto não há variáveis de ambiente necessárias
   - As credenciais são enviadas via POST

5. **Deploy**
   - Clique em "Deploy"
   - Aguarde o build finalizar (1-2 minutos)

6. **Acesse sua aplicação**
   - Após o deploy, você receberá uma URL tipo: `https://seu-projeto.vercel.app`
   - Endpoint da API: `https://seu-projeto.vercel.app/api/enviar`

## 📁 Estrutura do Projeto

```
.
├── api/
│   └── enviar.py           # API serverless de envio TISS
├── index.html              # Interface web
├── vercel.json             # Configuração do Vercel
├── requirements.txt        # Dependências Python
├── enviar_anexos_producao.py  # Script local (backup)
├── requirements.txt        # Dependências Python
└── README.md              # Este arquivo
```

## 🔧 Tecnologias Utilizadas

- **Backend:** Python (BaseHTTPRequestHandler)
- **Deploy:** Vercel Serverless Functions
- **Integração:** SOAP/XML com Orizon TISS
- **Versionamento:** Git/GitHub

## 📝 API Disponível

### POST /api/enviar
Envia documentos TISS para a operadora Orizon.

**Opção 1: Processar XML e extrair pacientes**
```json
{
  "codigo_prestador": "0000263036",
  "login": "LAB0186",
  "senha": "91a2ab8fbdd7884f7e32fd19694712a0",
  "registro_ans": "005711",
  "xml_content": "<xml>conteúdo do XML TISS...</xml>"
}
```

**Response:**
```json
{
  "success": true,
  "message": "XML processado com sucesso",
  "total_pacientes": 5,
  "pacientes": [
    {
      "numeroLote": "4219",
      "numeroGuiaPrestador": "12345",
      "numeroGuiaOperadora": "67890",
      "carteirinha": "123456789",
      "numeroProtocolo": "2024001",
      "numeroDocumento": "12345001"
    }
  ]
}
```

**Opção 2: Enviar documento diretamente**
```json
{
  "codigo_prestador": "0000263036",
  "login": "LAB0186",
  "senha": "91a2ab8fbdd7884f7e32fd19694712a0",
  "registro_ans": "005711",
  "numero_lote": "4219",
  "numero_protocolo": "2024001",
  "numero_guia_prestador": "12345",
  "numero_guia_operadora": "67890",
  "numero_documento": "12345001",
  "pdf_base64": "JVBERi0xLjQK...",
  "natureza_guia": "2",
  "tipo_documento": "01",
  "observacao": ""
}
```

**Response:**
```json
{
  "success": true,
  "resultado": {
    "success": true,
    "status_code": 200,
    "response": "<?xml...>",
    "tentativas": 1
  }
}
```

## 🔄 Atualizações Automáticas

Toda vez que você fizer push para o branch `master` no GitHub, o Vercel automaticamente:
1. Detecta as mudanças
2. Faz o rebuild do projeto
3. Publica a nova versão

## 🐛 Troubleshooting

### Erro "Module not found"
- Verifique se o `requirements.txt` está correto (não `Requeriments.txt`)
- Confirme que está usando Python 3.9+

### Erro "Function timeout"
- O Vercel tem limite de 10s (gratuito) ou 60s (pro)
- Para arquivos grandes, considere dividir em múltiplas requisições

### Erro CORS
- Os headers CORS já estão configurados no código
- Aceita requisições de qualquer origem (*)

### Erro de autenticação Orizon
- Verifique as credenciais (codigo_prestador, login, senha)
- A senha pode ser texto puro ou MD5 (será convertida automaticamente)

## 🔐 Segurança

⚠️ **IMPORTANTE:** As credenciais são enviadas via POST no corpo da requisição. Para produção:
- Use HTTPS (o Vercel já fornece)
- Considere adicionar autenticação JWT
- Não exponha as credenciais no frontend

## 📦 Dependências

- `requests==2.31.0` - Para requisições HTTP ao webservice Orizon

## 📞 Suporte

Em caso de dúvidas ou problemas, entre em contato com a equipe de TI do LAB.

---

**Desenvolvido por LAB Medicina Diagnóstica** 🏥
