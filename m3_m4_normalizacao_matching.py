import pandas as pd
import json
from openai import OpenAI
from sklearn.metrics.pairwise import cosine_similarity
from sklearn.feature_extraction.text import TfidfVectorizer

CHAVE = "SUA_CHAVE_AQUI"
client = OpenAI(api_key=CHAVE)

lpu = pd.read_parquet("lpu_atributos.parquet")
sinapi = pd.read_parquet("lpu_atributos.parquet").pipe(lambda _: pd.read_excel("planilha_obras.xlsx", sheet_name="itens_sinapi"))
sinapi.columns = ["classificacao", "codigo", "descricao", "unidade", "preco_sp"]
sinapi = sinapi.dropna(subset=["descricao"]).reset_index(drop=True)

SYSTEM_SINAPI = """Você é especialista em orçamentos de obras de edificação.
Dado um item SINAPI, retorne APENAS um JSON válido com exatamente estas chaves:
- produto_base: nome genérico do produto (ex: "porta", "cabo", "tubo", "tomada")
- categoria: disciplina da obra (ex: "elétrica", "hidráulica", "esquadrias", "sinalização", "civil")
- material_principal: material predominante ou null
- dimensoes: objeto com pares chave-valor numéricos ou null
- especificacoes_tecnicas: objeto com specs ou null
- unidade_inferida: unidade de medida inferida (ex: "un", "m", "m²", "m³", "kg")"""

atributos_sinapi = []
for desc in sinapi["descricao"]:
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_SINAPI},
                {"role": "user",   "content": str(desc)}
            ],
            response_format={"type": "json_object"}
        )
        atributos_sinapi.append(json.loads(r.choices[0].message.content))
    except:
        atributos_sinapi.append({})

sinapi_attrs = pd.concat([sinapi, pd.DataFrame(atributos_sinapi)], axis=1)
sinapi_attrs.to_parquet("sinapi_atributos.parquet", index=False)

lpu   = pd.read_parquet("lpu_atributos.parquet")
sinapi_attrs = pd.read_parquet("sinapi_atributos.parquet")

def score_atributos(lpu_row, sin_row):
    score = 0.0
    if str(lpu_row.get("produto_base","")).lower() != str(sin_row.get("produto_base","")).lower():
        return 0.0
    if str(lpu_row.get("categoria","")).lower() == str(sin_row.get("categoria","")).lower():
        score += 0.30
    if str(lpu_row.get("material_principal","")).lower() == str(sin_row.get("material_principal","")).lower():
        score += 0.30
    dim_l = lpu_row.get("dimensoes") or {}
    dim_s = sin_row.get("dimensoes") or {}
    if isinstance(dim_l, str): dim_l = json.loads(dim_l)
    if isinstance(dim_s, str): dim_s = json.loads(dim_s)
    if dim_l and dim_s and dim_l == dim_s:
        score += 0.25
    elif dim_l and dim_s:
        matches = sum(1 for k in dim_l if k in dim_s and abs(dim_l[k] - dim_s[k]) < 1)
        score += 0.25 * (matches / max(len(dim_l), 1))
    esp_l = lpu_row.get("especificacoes_tecnicas") or {}
    esp_s = sin_row.get("especificacoes_tecnicas") or {}
    if isinstance(esp_l, str): esp_l = json.loads(esp_l)
    if isinstance(esp_s, str): esp_s = json.loads(esp_s)
    if esp_l and esp_s:
        matches = sum(1 for k in esp_l if k in esp_s and str(esp_l[k]) == str(esp_s[k]))
        score += 0.15 * (matches / max(len(esp_l), 1))
    return round(score, 4)

resultados = []
for _, lpu_row in lpu.iterrows():
    produto = str(lpu_row.get("produto_base", "")).lower()
    candidatos = sinapi_attrs[sinapi_attrs["produto_base"].str.lower() == produto]
    if candidatos.empty:
        resultados.append({
            "lpu_codigo": lpu_row["codigo"],
            "lpu_descricao": lpu_row["descricao"],
            "sinapi_codigo": None,
            "sinapi_descricao": None,
            "preco_sp": None,
            "score": 0.0,
            "status": "SEM_MATCH"
        })
        continue
    scores = candidatos.apply(lambda r: score_atributos(lpu_row, r), axis=1)
    melhor_idx = scores.idxmax()
    melhor_score = scores[melhor_idx]
    melhor = candidatos.loc[melhor_idx]
    status = "MATCH" if melhor_score >= 0.6 else "REVISAR" if melhor_score >= 0.3 else "SEM_MATCH"
    resultados.append({
        "lpu_codigo": lpu_row["codigo"],
        "lpu_descricao": lpu_row["descricao"],
        "sinapi_codigo": melhor["codigo"],
        "sinapi_descricao": melhor["descricao"],
        "preco_sp": melhor["preco_sp"],
        "score": melhor_score,
        "status": status
    })

output = pd.DataFrame(resultados)
output.to_excel("resultado_matching.xlsx", index=False)
print(f"Concluído: {len(output)} itens → resultado_matching.xlsx")
print(output["status"].value_counts())
