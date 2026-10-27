# Web Scraper Portal G1 - Data Science

Este repositório contém o projeto de um **Web Scraper** desenvolvido em Python para a disciplina de **Data Science** do curso de Análise e Desenvolvimento de Sistemas (ADS) no **SENAC Pernambuco**, sob a orientação do Professor **Heuryk Wylk**.

O objetivo principal do projeto é realizar a extração automatizada de notícias, categorias e metadados de vídeo da página principal do portal de notícias G1, processar as informações utilizando a biblioteca Pandas e exportar os dados consolidados em arquivos no formato CSV.

---

## 🚀 Funcionalidades e Exercícios Práticos Desenvolvidos

O script foi expandido e modularizado para cobrir todos os requisitos obrigatórios e desafios propostos na atividade prática:

1. **Extração Profunda de Metadados (Exercício 1):** O scraper realiza requisições secundárias para a página interna de cada notícia minerada, coletando de forma automatizada:
   * Data e hora de publicação originais.
   * Autor/Crédito da matéria.
   * Contagem numérica de comentários.
2. **Sistema de Monitoramento e Logs (Exercício 2):** Implementação do módulo nativo `logging` do Python para geração do arquivo físico `scraper_g1.log`. O sistema registra:
   * O tempo total exato de execução do script.
   * A volumetria e distribuição de notícias capturadas por categoria.
   * Rastreamento detalhado de falhas e exceções estruturais sem interrupção da esteira de dados.
3. **Mecanismo de Filtro e Ordenação por Relevância (Exercício 3):**
   * Coleta de URLs de imagens integradas às notícias (`og:image`).
   * Limpeza de dados para retenção exclusiva de links válidos e ativos.
   * Ordenação decrescente do DataFrame final com base no engajamento da comunidade (número de comentários).
4. **Validador de Links Defensivo (Exercício 4):** Função dedicada a inspecionar os links extraídos utilizando requisições leves de cabeçalho (`requests.head`), mapeando o status de conexão, identificando redirecionamentos automáticos e sinalizando links quebrados.

---

## 📦 Estrutura do Projeto

```text
├── .venv/                  # Ambiente virtual isolado (ignorado pelo Git)
├── .gitignore              # Regras de exclusão de arquivos locais do Git
├── Web_Scraper_G1.py       # Código-fonte principal do Scraper em Python
├── categorias_g1.csv       # Arquivo de saída contendo as categorias do menu mapeadas
├── noticias_g1_expandido.csv# Base de dados estruturada das notícias extraídas e enriquecidas
├── scraper_g1.log          # Arquivo de logs gerado automaticamente em runtime
└── README.md               # Documentação oficial do projeto
```

---

## 🛠️ Tecnologias Utilizadas

* **Python 3.x**
* **Requests:** Requisições HTTP e validação de conexões.
* **BeautifulSoup4 (bs4):** Parsing do documento HTML e manipulação de seletores CSS.
* **Pandas:** Estruturação de DataFrames, tratamento de duplicatas, filtragem, ordenação e exportação de arquivos CSV.
* **Logging & Datetime:** Rastreamento operacional e registros cronológicos.

---

## 🔧 Como Executar o Projeto Localmente

### 1. Clonar o Repositório
```bash
git clone https://github.com/juanvalongo/Web-Scraper-G1.git
cd Web-Scraper-G1
```

### 2. Configurar e Ativar o Ambiente Virtual (venv)
```bash
# Criar o ambiente isolado
python -m venv .venv

# Ativar no Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Ativar no Linux/macOS
source .venv/bin/activate
```

### 3. Instalar as Dependências Externas
```bash
pip install requests pandas beautifulsoup4
```

### 4. Executar o Script
```bash
python Web_Scraper_G1.py
```

Após a finalização da execução, as bases de dados `categorias_g1.csv` e `noticias_g1_expandido.csv` serão geradas ou atualizadas na raiz do diretório, acompanhadas do relatório gerado no arquivo `scraper_g1.log`.
