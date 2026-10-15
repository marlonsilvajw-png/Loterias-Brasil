"""Loterias Brasil — servidor MCP experimental.

Fonte de dados: endpoints públicos do portal Loterias CAIXA.
Projeto independente, sem vínculo oficial com a CAIXA.
"""

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("Loterias Brasil", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))

MODALIDADES = {
    "megasena": "Mega-Sena",
    "lotofacil": "Lotofácil",
    "quina": "Quina",
    "lotomania": "Lotomania",
}

BASE_URL = "https://servicebus2.caixa.gov.br/portaldeloterias/api"


def _modalidade(nome: str) -> str:
    chave = nome.lower().strip().replace("-", "").replace(" ", "")
    if chave not in MODALIDADES:
        raise ValueError("Modalidade inválida. Use: megasena, lotofacil, quina ou lotomania.")
    return chave


async def _resultado(modalidade: str, concurso: int | None = None) -> dict[str, Any]:
    chave = _modalidade(modalidade)
    if concurso is not None and concurso < 1:
        raise ValueError("O número do concurso deve ser positivo.")
    url = f"{BASE_URL}/{chave}"
    if concurso is not None:
        url += f"/{concurso}"
    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
            resposta = await client.get(url, headers={"Accept": "application/json"})
            resposta.raise_for_status()
            dados = resposta.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise RuntimeError(
            "Não foi possível consultar os dados da CAIXA neste momento. "
            "Tente novamente mais tarde e confira o resultado no portal oficial."
        ) from exc
    if not isinstance(dados, dict) or not isinstance(dados.get("listaDezenas"), list):
        raise RuntimeError("A fonte retornou dados inesperados; não é seguro informar um resultado.")
    return dados


def _resumo(dados: dict[str, Any], modalidade: str) -> dict[str, Any]:
    return {
        "modalidade": MODALIDADES[modalidade],
        "concurso": dados.get("numero"),
        "data": dados.get("dataApuracao"),
        "dezenas": dados.get("listaDezenas"),
        "acumulado": dados.get("acumulado"),
        "premiacoes": dados.get("listaRateioPremio"),
        "proximo_concurso": dados.get("numeroConcursoProximo"),
        "estimativa_proximo_premio": dados.get("valorEstimadoProximoConcurso"),
        "fonte": "Portal Loterias CAIXA (dados consultados em tempo real)",
        "aviso": "Confira informações de premiação no site oficial da CAIXA.",
    }


@mcp.tool()
async def consultar_resultado(modalidade: str, concurso: int | None = None) -> dict[str, Any]:
    """Consulta o último resultado ou um concurso específico.

    modalidade: megasena, lotofacil, quina ou lotomania.
    concurso: número opcional; sem ele, consulta o resultado mais recente.
    """
    chave = _modalidade(modalidade)
    dados = await _resultado(chave, concurso)
    return _resumo(dados, chave)


@mcp.tool()
async def conferir_aposta(modalidade: str, numeros: list[int], concurso: int) -> dict[str, Any]:
    """Confere números de uma aposta contra um concurso já realizado.

    Não substitui a validação do bilhete pela CAIXA. Não calcula
    premiações de apostas múltiplas nem substitui regras oficiais.
    """
    chave = _modalidade(modalidade)
    regras = {
        "megasena": (6, 20, 1, 60),
        "lotofacil": (15, 20, 1, 25),
        "quina": (5, 15, 1, 80),
        "lotomania": (50, 50, 0, 99),
    }
    minimo, maximo, inicio, fim = regras[chave]
    if not minimo <= len(numeros) <= maximo:
        raise ValueError(f"Informe entre {minimo} e {maximo} números para {MODALIDADES[chave]}.")
    if len(set(numeros)) != len(numeros) or any(type(n) is not int or not inicio <= n <= fim for n in numeros):
        raise ValueError(f"Use números inteiros distintos entre {inicio} e {fim}.")
    dados = await _resultado(chave, concurso)
    sorteadas = {int(n) for n in dados["listaDezenas"]}
    acertos = sorted(set(numeros) & sorteadas)
    return {
        "modalidade": MODALIDADES[chave],
        "concurso": dados.get("numero"),
        "data": dados.get("dataApuracao"),
        "numeros_apostados": sorted(numeros),
        "numeros_sorteados": sorted(sorteadas),
        "numeros_acertados": acertos,
        "quantidade_acertos": len(acertos),
        "faixas_premiacao_do_concurso": dados.get("listaRateioPremio"),
        "aviso": "Contagem informativa de acertos. A premiação efetiva depende das regras oficiais, do tipo de aposta e da validação do bilhete pela CAIXA.",
    }


if __name__ == "__main__":
    # Hospedagens exigem um servidor HTTP acessível publicamente.
    # O caminho /mcp será usado na conexão com o ChatGPT.
    mcp.run(transport="streamable-http")
