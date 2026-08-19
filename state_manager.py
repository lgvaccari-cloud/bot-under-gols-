"""
Persistência simples em JSON, salva em disco persistente (config.STATE_FILE_PATH).

Estrutura do estado:
{
  "banca_atual": 100000.0,
  "jogos_alertados": ["<fi>", ...],           # jogos que já geraram alerta (não alerta 2x)
  "apostas_abertas": {
      "<id_aposta>": {
          "fi": "...", "time_casa": "...", "time_fora": "...",
          "liga": "...", "pais": "...", "linha": 3.5, "odd": 1.85,
          "data_abertura": "2026-08-19", "stake": 1000.0
      }
  },
  "resumo_dia": {"data": "2026-08-19", "total": 0, "greens": 0, "reds": 0, "voids_e_meios": 0, "resultado": 0.0}
}
"""
import json
import os
import threading

import config

_lock = threading.Lock()

_ESTADO_PADRAO = {
    "banca_atual": config.BANCA_INICIAL,
    "jogos_alertados": [],
    "apostas_abertas": {},
    "resumo_dia": {"data": "", "total": 0, "greens": 0, "reds": 0, "voids_e_meios": 0, "resultado": 0.0},
}


def carregar_estado() -> dict:
    with _lock:
        if not os.path.exists(config.STATE_FILE_PATH):
            return json.loads(json.dumps(_ESTADO_PADRAO))
        try:
            with open(config.STATE_FILE_PATH, "r", encoding="utf-8") as f:
                estado = json.load(f)
            # garante que todas as chaves padrão existem (upgrade de versão)
            for chave, valor in _ESTADO_PADRAO.items():
                estado.setdefault(chave, valor)
            return estado
        except (json.JSONDecodeError, OSError):
            return json.loads(json.dumps(_ESTADO_PADRAO))


def salvar_estado(estado: dict):
    with _lock:
        os.makedirs(os.path.dirname(config.STATE_FILE_PATH), exist_ok=True)
        caminho_tmp = config.STATE_FILE_PATH + ".tmp"
        with open(caminho_tmp, "w", encoding="utf-8") as f:
            json.dump(estado, f, ensure_ascii=False, indent=2)
        os.replace(caminho_tmp, config.STATE_FILE_PATH)
