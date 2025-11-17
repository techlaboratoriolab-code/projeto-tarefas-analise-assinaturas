# LAB - Sistema de Processamento XML TISS

Sistema web para processamento de arquivos XML no padrão TISS, desenvolvido para o LAB Medicina Diagnóstica.

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
   - **Root Directory:** `Desktop/automação lotes Orizon`
   - **Build Command:** (deixe vazio)
   - **Output Directory:** (deixe vazio)

4. **Variáveis de Ambiente** (se necessário)
   - Por enquanto não há variáveis de ambiente necessárias

5. **Deploy**
   - Clique em "Deploy"
   - Aguarde o build finalizar (1-2 minutos)

6. **Acesse sua aplicação**
   - Após o deploy, você receberá uma URL tipo: `https://seu-projeto.vercel.app`
   - Teste as APIs:
     - Health check: `https://seu-projeto.vercel.app/api/health`
     - Interface: `https://seu-projeto.vercel.app/`

## 📁 Estrutura do Projeto

```
.
├── api/
│   ├── process.py      # API principal de processamento XML
│   └── health.py       # Health check
├── index.html          # Interface web
├── vercel.json         # Configuração do Vercel
├── Requeriments.txt    # Dependências Python
└── README.md           # Este arquivo
```

## 🔧 Tecnologias Utilizadas

- **Backend:** Python (BaseHTTPRequestHandler)
- **Frontend:** HTML5, CSS3, JavaScript vanilla
- **Deploy:** Vercel
- **Versionamento:** Git/GitHub

## 📝 APIs Disponíveis

### POST /api/process
Processa arquivos XML no padrão TISS e extrai informações de guias.

**Request:**
- Content-Type: `multipart/form-data`
- Body: Arquivos XML (campo `files`)

**Response:**
```json
{
  "success": true,
  "resultados": [
    {
      "arquivo": "exemplo.xml",
      "total_pacientes": 2,
      "pacientes": [
        {
          "guia": "12345",
          "carteirinha": "123456789",
          "lote": "4219",
          "protocolo": "2024001",
          "status": "✓ Dados extraídos com sucesso"
        }
      ]
    }
  ]
}
```

### GET /api/health
Verifica se o serviço está funcionando.

**Response:**
```json
{
  "status": "ok",
  "service": "LAB TISS Processor",
  "version": "1.0.0"
}
```

## 🔄 Atualizações Automáticas

Toda vez que você fizer push para o branch `master` no GitHub, o Vercel automaticamente:
1. Detecta as mudanças
2. Faz o rebuild do projeto
3. Publica a nova versão

## 🐛 Troubleshooting

### Erro "Module not found"
- Verifique se o `Requeriments.txt` está correto
- Confirme que está usando Python 3.9+

### Erro "Function timeout"
- Verifique se os XMLs não são muito grandes
- O Vercel tem limite de 10s para execução no plano gratuito

### Erro CORS
- Os headers CORS já estão configurados no código
- Se persistir, verifique o console do navegador

## 📞 Suporte

Em caso de dúvidas ou problemas, entre em contato com a equipe de TI do LAB.

---

**Desenvolvido por LAB Medicina Diagnóstica** 🏥
