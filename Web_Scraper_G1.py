
import requests
import pandas as pd
import json
import logging
import time
import re

from collections import Counter
from datetime import datetime, date
from bs4 import BeautifulSoup
from urllib.parse import urljoin


# ============================================================
# 1. CONFIGURAÇÕES
# ============================================================

URL = "https://g1.globo.com/"

# Formato: AAAA-MM-DD
# Use None para não aplicar limite.
DATA_INICIAL = None       # Ex.: "2026-10-01"
DATA_FINAL = None         # Ex.: "2026-10-27"

# Quantidade de notícias a processar.
# Use None para processar todas as encontradas.
LIMITE_NOTICIAS = None

ARQUIVO_NOTICIAS = "noticias_g1_expandido.csv"
ARQUIVO_CATEGORIAS = "categorias_g1.csv"
ARQUIVO_LOG = "extrator_g1.log"

headers = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    handlers=[
        logging.FileHandler(ARQUIVO_LOG, encoding="utf-8"),
        logging.StreamHandler()
    ],
    force=True
)

logger = logging.getLogger("extrator_g1")

session = requests.Session()
session.headers.update(headers)

def validar_link(url, timeout=15):
    """
    Valida um link, identifica redirecionamentos e registra erros.

    Retorna:
        status_link: resultado da validação
        status_http: código HTTP da resposta
        url_final: URL após os redirecionamentos
        redirecionado: Sim ou Não
        detalhe_validacao: informação adicional
    """

    resultado = {
        "status_link": "Não validado",
        "status_http": None,
        "url_final": url or "",
        "redirecionado": "Não",
        "detalhe_validacao": ""
    }

    if not url or not url.startswith(("http://", "https://")):
        resultado["status_link"] = "URL inválida"
        resultado["detalhe_validacao"] = "Endereço ausente ou inválido."

        registrar_aviso(
            "Validação de links",
            f"URL inválida: {url}"
        )
        return resultado

    resposta = None

    try:
        # HEAD verifica os cabeçalhos sem baixar todo o conteúdo.
        resposta = session.head(
            url,
            allow_redirects=True,
            timeout=timeout
        )

        # Alguns servidores não permitem HEAD.
        if resposta.status_code in (403, 405, 501):
            resposta.close()
            resposta = session.get(
                url,
                allow_redirects=True,
                timeout=timeout,
                stream=True
            )

        status = resposta.status_code
        url_final = resposta.url or url

        redirecionado = (
            len(resposta.history) > 0
            or url_final.rstrip("/") != url.rstrip("/")
        )

        resultado["status_http"] = status
        resultado["url_final"] = url_final
        resultado["redirecionado"] = (
            "Sim" if redirecionado else "Não"
        )

        if 200 <= status < 300:
            resultado["status_link"] = "Ativo"
            resultado["detalhe_validacao"] = (
                "Resposta HTTP bem-sucedida."
            )

        elif 300 <= status < 400:
            resultado["status_link"] = "Redirecionamento não concluído"
            resultado["detalhe_validacao"] = (
                "O servidor retornou uma resposta de redirecionamento."
            )

        elif status in (401, 403, 407):
            resultado["status_link"] = "Acesso restrito"
            resultado["detalhe_validacao"] = (
                "O servidor restringiu o acesso; o link pode existir."
            )

        elif status == 404 or status == 410:
            resultado["status_link"] = "Quebrado"
            resultado["detalhe_validacao"] = (
                "Página não encontrada ou conteúdo removido."
            )

        elif status >= 400:
            resultado["status_link"] = "Erro HTTP"
            resultado["detalhe_validacao"] = (
                f"O servidor retornou HTTP {status}."
            )

        if redirecionado:
            logger.info(
                "Redirecionamento identificado: %s -> %s",
                url,
                url_final
            )

        if resultado["status_link"] in (
            "Quebrado",
            "Erro HTTP",
            "Redirecionamento não concluído"
        ):
            registrar_erro(
                "Validação de links",
                f"{url} | HTTP {status} | {resultado['status_link']}"
            )

        elif resultado["status_link"] == "Acesso restrito":
            registrar_aviso(
                "Validação de links",
                f"{url} | HTTP {status} | acesso restrito"
            )

    except requests.RequestException as erro:
        resultado["status_link"] = "Erro de conexão"
        resultado["detalhe_validacao"] = str(erro)

        registrar_erro(
            "Validação de links",
            f"{url} | {erro}"
        )

    finally:
        if resposta is not None:
            resposta.close()

    return resultado


inicio_total = time.perf_counter()
data_inicio_execucao = datetime.now()

categorias = []
noticias = []
erros = Counter()
avisos = Counter()
tempos = {}


# Validar o período antes de fazer requisições.
try:
    data_inicial = (
        date.fromisoformat(DATA_INICIAL)
        if DATA_INICIAL else None
    )
    data_final = (
        date.fromisoformat(DATA_FINAL)
        if DATA_FINAL else None
    )

    if data_inicial and data_final and data_inicial > data_final:
        raise ValueError(
            "A data inicial não pode ser posterior à data final."
        )

except ValueError as erro:
    raise SystemExit(f"Configuração de datas inválida: {erro}")


# ============================================================
# 2. FUNÇÕES DE LOG
# ============================================================

def registrar_erro(etapa, mensagem):
    erros[etapa] += 1
    logger.error("%s: %s", etapa, mensagem)


def registrar_aviso(etapa, mensagem):
    avisos[etapa] += 1
    logger.warning("%s: %s", etapa, mensagem)


def marcar_tempo(etapa, inicio):
    duracao = time.perf_counter() - inicio
    tempos[etapa] = tempos.get(etapa, 0) + duracao
    return duracao


# ============================================================
# 3. FUNÇÕES AUXILIARES
# ============================================================

def obter_texto(elemento):
    if elemento:
        return elemento.get_text(" ", strip=True)
    return ""


def obter_imagem_elemento(elemento, base_url):
    """Obtém a URL de uma imagem HTML, inclusive lazy loading."""

    if not elemento:
        return None

    for atributo in (
        "data-src",
        "data-original",
        "data-lazy-src",
        "src"
    ):
        valor = elemento.get(atributo)

        if valor and not valor.startswith("data:"):
            return urljoin(base_url, valor)

    # Algumas imagens usam srcset ou data-srcset.
    for atributo in ("data-srcset", "srcset"):
        valor = elemento.get(atributo)

        if valor:
            candidatos = []

            for parte in valor.split(","):
                partes = parte.strip().split()

                if partes:
                    candidatos.append(partes[0])

            if candidatos:
                return urljoin(base_url, candidatos[-1])

    return None


def extrair_imagem(soup, base_url):
    """
    Prioridade:
    1. og:image
    2. twitter:image
    3. imagem principal declarada em JSON-LD
    4. imagem do artigo ou primeira imagem útil.
    """

    for seletor in (
        'meta[property="og:image"]',
        'meta[name="twitter:image"]',
        'meta[property="twitter:image"]'
    ):
        elemento = soup.select_one(seletor)

        if elemento and elemento.get("content"):
            imagem = urljoin(base_url, elemento["content"])

            if imagem.startswith(("http://", "https://")):
                return imagem

    # Procurar imagens nos dados estruturados.
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            dados = json.loads(script.string or script.get_text())
            pilha = dados if isinstance(dados, list) else [dados]

            while pilha:
                item = pilha.pop(0)

                if not isinstance(item, dict):
                    continue

                imagem = item.get("image")

                if isinstance(imagem, str):
                    return urljoin(base_url, imagem)

                if isinstance(imagem, dict):
                    url_imagem = (
                        imagem.get("url")
                        or imagem.get("contentUrl")
                    )
                    if url_imagem:
                        return urljoin(base_url, url_imagem)

                if isinstance(imagem, list):
                    for candidato in imagem:
                        if isinstance(candidato, str):
                            return urljoin(base_url, candidato)
                        if isinstance(candidato, dict):
                            url_imagem = (
                                candidato.get("url")
                                or candidato.get("contentUrl")
                            )
                            if url_imagem:
                                return urljoin(base_url, url_imagem)

                if isinstance(item.get("@graph"), list):
                    pilha.extend(item["@graph"])

        except (json.JSONDecodeError, TypeError, AttributeError):
            continue

    # Tentar localizar imagens no conteúdo editorial.
    for seletor in (
        "article img",
        "figure img",
        ".content-media img",
        ".mc-article-body img",
        "main img"
    ):
        for elemento in soup.select(seletor):
            imagem = obter_imagem_elemento(elemento, base_url)

            if imagem and imagem.startswith(("http://", "https://")):
                return imagem

    return None


def interpretar_data(valor):
    """Converte datas ISO e formatos comuns para datetime."""

    if not valor or valor == "Não disponível":
        return None

    valor = str(valor).strip()

    try:
        resultado = datetime.fromisoformat(
            valor.replace("Z", "+00:00")
        )
        # Remover fuso horário para comparação consistente
        # com os limites de data informados pelo usuário.
        return resultado.replace(tzinfo=None)

    except ValueError:
        pass

    formatos = (
        "%Y-%m-%d",
        "%Y-%m-%d %H:%M:%S",
        "%d/%m/%Y",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%dT%H:%M:%S"
    )

    for formato in formatos:
        try:
            return datetime.strptime(valor, formato)
        except ValueError:
            continue

    return None


# ============================================================
# 4. EXTRAÇÃO DE METADADOS
# ============================================================

def extrair_metadados(soup, url_pagina):
    resultado = {
        "data_publicacao": "Não disponível",
        "autor": "Não disponível",
        "numero_comentarios": "Não disponível",
        "imagem": extrair_imagem(soup, url_pagina)
    }

    # Dados estruturados JSON-LD
    for script in soup.select(
        'script[type="application/ld+json"]'
    ):
        try:
            dados = json.loads(script.string or script.get_text())
            pilha = dados if isinstance(dados, list) else [dados]

            while pilha:
                item = pilha.pop(0)

                if not isinstance(item, dict):
                    continue

                tipo = item.get("@type", [])
                tipos = tipo if isinstance(tipo, list) else [tipo]

                if any(
                    t in (
                        "NewsArticle",
                        "Article",
                        "ReportageNewsArticle"
                    )
                    for t in tipos
                ):
                    if resultado["data_publicacao"] == "Não disponível":
                        resultado["data_publicacao"] = (
                            item.get("datePublished")
                            or "Não disponível"
                        )

                    if resultado["autor"] == "Não disponível":
                        autor_dados = item.get("author")

                        if isinstance(autor_dados, list):
                            nomes = [
                                autor.get("name", "")
                                for autor in autor_dados
                                if isinstance(autor, dict)
                                and autor.get("name")
                            ]

                            if nomes:
                                resultado["autor"] = ", ".join(nomes)

                        elif isinstance(autor_dados, dict):
                            resultado["autor"] = (
                                autor_dados.get("name")
                                or "Não disponível"
                            )

                        elif isinstance(autor_dados, str):
                            resultado["autor"] = autor_dados

                    if resultado["numero_comentarios"] == "Não disponível":
                        interacoes = item.get("interactionStatistic", [])

                        if isinstance(interacoes, dict):
                            interacoes = [interacoes]

                        for interacao in interacoes:
                            if not isinstance(interacao, dict):
                                continue

                            tipo_interacao = str(
                                interacao.get("interactionType", "")
                            ).lower()

                            if "comment" in tipo_interacao:
                                quantidade = interacao.get(
                                    "userInteractionCount"
                                )

                                if quantidade is not None:
                                    resultado["numero_comentarios"] = (
                                        quantidade
                                    )
                                    break

                if isinstance(item.get("@graph"), list):
                    pilha.extend(item["@graph"])

        except (json.JSONDecodeError, TypeError, AttributeError) as erro:
            registrar_aviso("JSON-LD", str(erro))

    # Data nas meta tags
    if resultado["data_publicacao"] == "Não disponível":
        elemento = soup.select_one(
            'meta[property="article:published_time"], '
            'meta[name="datePublished"], '
            'meta[itemprop="datePublished"]'
        )

        if elemento:
            resultado["data_publicacao"] = (
                elemento.get("content") or "Não disponível"
            )

    # Data em elemento time
    if resultado["data_publicacao"] == "Não disponível":
        elemento = soup.select_one("time[datetime]")

        if elemento:
            resultado["data_publicacao"] = (
                elemento.get("datetime")
                or obter_texto(elemento)
                or "Não disponível"
            )

    # Autor nas meta tags
    if resultado["autor"] == "Não disponível":
        elemento = soup.select_one(
            'meta[name="author"], meta[property="article:author"]'
        )

        if elemento:
            resultado["autor"] = (
                elemento.get("content") or "Não disponível"
            )

    # Autor no HTML
    if resultado["autor"] == "Não disponível":
        elemento = soup.select_one(
            '[rel="author"], '
            '[itemprop="author"] [itemprop="name"], '
            '.content-publication-data__from, '
            '.content-publication-data__agency'
        )

        if elemento:
            resultado["autor"] = (
                obter_texto(elemento) or "Não disponível"
            )

    # Contagem de comentários, quando exposta no HTML
    if resultado["numero_comentarios"] == "Não disponível":
        for elemento in soup.select(
            '[data-comment-count], [itemprop="commentCount"]'
        ):
            valor = (
                elemento.get("data-comment-count")
                or elemento.get("content")
                or obter_texto(elemento)
            )

            if valor:
                numero = re.search(r"\d+", str(valor))

                if numero:
                    resultado["numero_comentarios"] = int(
                        numero.group()
                    )
                    break

    return resultado


# ============================================================
# 5. ACESSAR A PÁGINA PRINCIPAL
# ============================================================

inicio = time.perf_counter()

logger.info("Iniciando extração do G1.")

try:
    resposta = session.get(URL, timeout=20)
    resposta.raise_for_status()

    soup = BeautifulSoup(resposta.text, "html.parser")

    logger.info(
        "Página principal carregada. Status HTTP: %s",
        resposta.status_code
    )

except requests.RequestException as erro:
    registrar_erro("Página principal", str(erro))
    logger.critical("Execução interrompida.")
    raise SystemExit(1)

finally:
    marcar_tempo("Página principal", inicio)


# ============================================================
# 6. EXTRAIR CATEGORIAS DO MENU
# ============================================================

inicio = time.perf_counter()

try:
    for item in soup.select(".menu-item"):
        link = item.get("href")
        nome = obter_texto(item)

        if link and nome:
            categorias.append({
                "nome": nome,
                "link": urljoin(URL, link)
            })

    logger.info("Categorias do menu: %d", len(categorias))

    if not categorias:
        registrar_aviso(
            "Categorias",
            "Nenhuma categoria encontrada pelos seletores atuais."
        )

except Exception as erro:
    registrar_erro("Categorias", str(erro))

finally:
    marcar_tempo("Categorias", inicio)


# ============================================================
# 7. EXTRAIR DESTAQUE PRINCIPAL
# ============================================================

inicio = time.perf_counter()

try:
    destaques = soup.select(".bastian-page")

    if destaques:
        principal = destaques[0].select_one(".bastian-cover")

        if principal:
            titulo_elemento = principal.select_one(
                "h1, .feed-post-body-title, .bstn-hl-title"
            )
            link_elemento = principal.select_one("a")

            if titulo_elemento:
                link = (
                    urljoin(URL, link_elemento.get("href"))
                    if link_elemento and link_elemento.get("href")
                    else "Link não disponível"
                )

                categoria_elemento = principal.select_one(
                    '[itemprop="articleSection"], '
                    ".feed-post-metadata-section"
                )

                noticias.append({
                    "titulo": obter_texto(titulo_elemento),
                    "link": link,
                    "tipo": "Destaque principal",
                    "categoria": (
                        obter_texto(categoria_elemento)
                        or "Não identificada"
                    ),
                    "imagem": obter_imagem_elemento(
                        principal.select_one("img"),
                        URL
                    )
                })

    if not noticias:
        registrar_aviso(
            "Destaque",
            "Não foi possível extrair o destaque principal."
        )

except Exception as erro:
    registrar_erro("Destaque principal", str(erro))

finally:
    marcar_tempo("Destaque", inicio)


# ============================================================
# 8. EXTRAIR NOTÍCIAS REGULARES
# ============================================================

inicio = time.perf_counter()

cards = soup.select(
    ".feed-post-body, .bstn-item, .bastian-feed-item"
)

logger.info("Cards encontrados: %d", len(cards))

for card in cards:
    try:
        titulo_elemento = card.select_one(
            ".feed-post-body-title, .bstn-hl-title"
        )

        if not titulo_elemento:
            avisos["Card sem título"] += 1
            continue

        link_elemento = card.select_one("a")

        link = (
            urljoin(URL, link_elemento.get("href"))
            if link_elemento and link_elemento.get("href")
            else "Link não disponível"
        )

        categoria_elemento = card.select_one(
            '[itemprop="articleSection"], '
            ".feed-post-metadata-section"
        )

        noticias.append({
            "titulo": obter_texto(titulo_elemento),
            "link": link,
            "tipo": "Notícia regular",
            "categoria": (
                obter_texto(categoria_elemento)
                or "Não identificada"
            ),
            "imagem": obter_imagem_elemento(
                card.select_one("img"),
                URL
            )
        })

    except Exception as erro:
        registrar_erro("Card de notícia", str(erro))

logger.info("Notícias coletadas antes de remover duplicatas: %d", len(noticias))

if avisos["Card sem título"]:
    registrar_aviso(
        "Cards",
        f"{avisos['Card sem título']} card(s) sem título foram ignorados."
    )

marcar_tempo("Cards", inicio)


# ============================================================
# 9. REMOVER DUPLICATAS ANTES DE ACESSAR AS NOTÍCIAS
# ============================================================

inicio = time.perf_counter()

noticias_unicas = []
chaves = set()

for noticia in noticias:
    link = noticia["link"]

    chave = (
        ("link", link)
        if link != "Link não disponível"
        else ("titulo", noticia["titulo"].strip().casefold())
    )

    if chave in chaves:
        continue

    chaves.add(chave)
    noticias_unicas.append(noticia)

logger.info(
    "Duplicatas removidas: %d",
    len(noticias) - len(noticias_unicas)
)

if LIMITE_NOTICIAS is not None:
    noticias_unicas = noticias_unicas[:max(0, LIMITE_NOTICIAS)]

logger.info("Notícias que serão processadas: %d", len(noticias_unicas))

marcar_tempo("Remoção de duplicatas", inicio)


# ============================================================
# 10. ENRIQUECER NOTÍCIAS COM METADADOS E IMAGENS
# ============================================================

inicio = time.perf_counter()

for indice, noticia in enumerate(noticias_unicas, start=1):
    logger.info(
        "Processando %d/%d: %s",
        indice,
        len(noticias_unicas),
        noticia["titulo"][:90]
    )

    metadados = {
        "data_publicacao": "Não disponível",
        "autor": "Não disponível",
        "numero_comentarios": "Não disponível"
    }

    if noticia["link"] != "Link não disponível":
        try:
            inicio_requisicao = time.perf_counter()

            resposta = session.get(noticia["link"], timeout=20)
            resposta.raise_for_status()

            pagina = BeautifulSoup(resposta.text, "html.parser")

            metadados = extrair_metadados(
                pagina,
                noticia["link"]
            )

            # Preferir a imagem da página da notícia, mas preservar
            # a imagem do card se a página não fornecer uma.
            if metadados.get("imagem"):
                noticia["imagem"] = metadados["imagem"]

            duracao = time.perf_counter() - inicio_requisicao

            logger.info(
                "Página processada em %.2f segundos.",
                duracao
            )

        except requests.RequestException as erro:
            registrar_erro(
                "Página da notícia",
                f"{noticia['link']} | {erro}"
            )

        except Exception as erro:
            registrar_erro(
                "Metadados da notícia",
                f"{noticia['titulo']} | {erro}"
            )

    else:
        registrar_aviso(
            "Link indisponível",
            f"Não foi possível consultar: {noticia['titulo']}"
        )

    noticia.update(metadados)
    
    # Validar o link da notícia
    resultado_link = validar_link(noticia.get("link"))

    noticia.update(resultado_link)

    if not noticia.get("imagem"):
        noticia["imagem"] = "Não disponível"
        avisos["Imagem indisponível"] += 1

    if noticia["data_publicacao"] == "Não disponível":
        avisos["Data indisponível"] += 1

    if noticia["autor"] == "Não disponível":
        avisos["Autor indisponível"] += 1

    if noticia["numero_comentarios"] == "Não disponível":
        avisos["Comentários indisponíveis"] += 1

    noticia["data_extracao"] = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

marcar_tempo("Metadados e imagens", inicio)


# ============================================================
# 11. FILTRAR POR DATA DE PUBLICAÇÃO
# ============================================================

inicio = time.perf_counter()

noticias_filtradas = []
excluidas_por_data = 0

for noticia in noticias_unicas:
    data_publicacao = interpretar_data(
        noticia.get("data_publicacao")
    )

    # Sem filtro configurado, preserva notícias sem data.
    if not data_inicial and not data_final:
        noticias_filtradas.append(noticia)
        continue

    # Com filtro ativo, não é possível confirmar o período
    # de notícias cuja data de publicação não foi encontrada.
    if data_publicacao is None:
        excluidas_por_data += 1
        continue

    dia_publicacao = data_publicacao.date()

    if data_inicial and dia_publicacao < data_inicial:
        excluidas_por_data += 1
        continue

    if data_final and dia_publicacao > data_final:
        excluidas_por_data += 1
        continue

    noticias_filtradas.append(noticia)

logger.info("Filtro de data inicial: %s", DATA_INICIAL or "Sem limite")
logger.info("Filtro de data final: %s", DATA_FINAL or "Sem limite")
logger.info("Notícias após filtro de data: %d", len(noticias_filtradas))
logger.info("Notícias excluídas pelo filtro: %d", excluidas_por_data)

if (data_inicial or data_final) and excluidas_por_data:
    registrar_aviso(
        "Filtro de data",
        f"{excluidas_por_data} notícia(s) excluídas, "
        "incluindo possíveis registros sem data identificável."
    )

marcar_tempo("Filtro de data", inicio)


# ============================================================
# 12. CALCULAR RELEVÂNCIA
# ============================================================

def calcular_relevancia(noticia):
    """
    Pontuação heurística.
    Não representa visualizações, audiência ou popularidade real.
    """

    pontuacao = 0

    # Destaque na página inicial
    if noticia.get("tipo") == "Destaque principal":
        pontuacao += 5

    # Imagem disponível
    imagem = noticia.get("imagem")
    if imagem and imagem != "Não disponível":
        pontuacao += 2

    # Data de publicação disponível
    if noticia.get("data_publicacao") != "Não disponível":
        pontuacao += 1

    # Autor disponível
    if noticia.get("autor") != "Não disponível":
        pontuacao += 1

    # Categoria editorial identificada
    categoria = noticia.get("categoria", "")
    if categoria and categoria != "Não identificada":
        pontuacao += 1

    # Link válido
    link = noticia.get("link", "")
    if link.startswith(("http://", "https://")):
        pontuacao += 1

    return pontuacao


inicio = time.perf_counter()

for noticia in noticias_filtradas:
    noticia["relevancia"] = calcular_relevancia(noticia)

noticias_ordenadas = sorted(
    noticias_filtradas,
    key=lambda noticia: (
        noticia["relevancia"],
        interpretar_data(noticia.get("data_publicacao"))
        or datetime.min
    ),
    reverse=True
)

logger.info("Notícias ordenadas por relevância decrescente.")

marcar_tempo("Ordenação por relevância", inicio)


# ============================================================
# 13. CONTAGEM POR TIPO E CATEGORIA
# ============================================================

contagem_tipos = Counter(
    noticia.get("tipo", "Não identificado")
    for noticia in noticias_ordenadas
)

contagem_categorias = Counter(
    noticia.get("categoria", "Não identificada")
    for noticia in noticias_ordenadas
)

logger.info("========== NOTÍCIAS POR TIPO ==========")

for tipo, quantidade in sorted(contagem_tipos.items()):
    logger.info("%s: %d", tipo, quantidade)

logger.info("========== NOTÍCIAS POR CATEGORIA ==========")

for categoria, quantidade in sorted(contagem_categorias.items()):
    logger.info("%s: %d", categoria, quantidade)


# ============================================================
# 14. SALVAR CSVs
# ============================================================

inicio = time.perf_counter()

colunas_noticias = [
    "titulo",
    "link",
    "tipo",
    "categoria",
    "data_publicacao",
    "autor",
    "numero_comentarios",
    "imagem",
    "relevancia",
    "data_extracao",
    "status_link",
    "status_http",
    "url_final",
    "redirecionado",
    "detalhe_validacao"
]

try:
    df = pd.DataFrame(
        noticias_ordenadas,
        columns=colunas_noticias
    )

    df.to_csv(
        ARQUIVO_NOTICIAS,
        index=False,
        encoding="utf-8-sig"
    )

    logger.info(
        "CSV de notícias salvo: %s (%d registros).",
        ARQUIVO_NOTICIAS,
        len(df)
    )

except (OSError, PermissionError, ValueError) as erro:
    registrar_erro("Salvamento de notícias", str(erro))

try:
    df_categorias = pd.DataFrame(
        categorias,
        columns=["nome", "link"]
    )

    df_categorias.to_csv(
        ARQUIVO_CATEGORIAS,
        index=False,
        encoding="utf-8-sig"
    )

    logger.info(
        "CSV de categorias salvo: %s (%d registros).",
        ARQUIVO_CATEGORIAS,
        len(df_categorias)
    )

except (OSError, PermissionError, ValueError) as erro:
    registrar_erro("Salvamento de categorias", str(erro))

marcar_tempo("Salvamento dos CSVs", inicio)


# ============================================================
# 15. RESUMO FINAL E TEMPO TOTAL
# ============================================================

duracao_total = time.perf_counter() - inicio_total

logger.info("================ RESUMO FINAL ================")
logger.info(
    "Início: %s",
    data_inicio_execucao.strftime("%Y-%m-%d %H:%M:%S")
)
logger.info(
    "Fim: %s",
    datetime.now().strftime("%Y-%m-%d %H:%M:%S")
)
logger.info("Tempo total: %.2f segundos", duracao_total)

for etapa, duracao in tempos.items():
    logger.info("Tempo - %s: %.2f segundos", etapa, duracao)

logger.info("Categorias do menu: %d", len(categorias))
logger.info("Notícias após filtro: %d", len(noticias_ordenadas))
logger.info("Total de erros: %d", sum(erros.values()))
logger.info("Total de avisos: %d", sum(avisos.values()))

if erros:
    logger.info("========== ERROS POR ETAPA ==========")

    for etapa, quantidade in erros.items():
        logger.info("%s: %d", etapa, quantidade)

if avisos:
    logger.info("========== AVISOS POR TIPO ==========")

    for etapa, quantidade in avisos.items():
        logger.info("%s: %d", etapa, quantidade)

logger.info("========== FIM DA EXECUÇÃO ==========")
