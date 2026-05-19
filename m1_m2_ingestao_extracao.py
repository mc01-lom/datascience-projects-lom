import pandas as pd
import json
from openai import OpenAI

ARQUIVO = "planilha_obras.xlsx"
CHAVE   = "SUA_CHAVE_AQUI"

client = OpenAI(api_key=CHAVE)

lpu = pd.read_excel(ARQUIVO, sheet_name="obras_empresa", usecols="B:C", header=0)
lpu.columns = ["codigo", "descricao"]
lpu = lpu.dropna(subset=["descricao"]).reset_index(drop=True)

sinapi = pd.read_excel(ARQUIVO, sheet_name="itens_sinapi")
sinapi.columns = ["classificacao", "codigo", "descricao", "unidade", "preco_sp"]
sinapi = sinapi.dropna(subset=["descricao"]).reset_index(drop=True)

SYSTEM = """Você é especialista em orçamentos de obras de edificação.
Dado um item de obra, retorne APENAS um JSON válido com exatamente estas chaves:
- produto_base: nome genérico do produto (ex: "porta", "cabo", "tubo", "tomada")
- categoria: disciplina da obra (ex: "elétrica", "hidráulica", "esquadrias", "sinalização", "civil")
- material_principal: material predominante ou null (ex: "cobre", "PVC", "chapa de aço")
- dimensoes: objeto com pares chave-valor numéricos ou null (ex: {"largura_cm": 90, "altura_cm": 210})
- especificacoes_tecnicas: objeto com specs ou null (ex: {"tensao_v": 250, "classe": 70, "nbr": "13248"})
- servicos_inclusos: lista de strings ou [] (ex: ["instalação", "fornecimento"])
- unidade_inferida: unidade de medida inferida (ex: "un", "m", "m²", "m³", "kg")
Ignore marcas comerciais. Normalize dimensões para centímetros ou metros conforme convenção da área."""

atributos = []
for desc in lpu["descricao"]:
    try:
        r = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": str(desc)}
            ],
            response_format={"type": "json_object"}
        )
        atributos.append(json.loads(r.choices[0].message.content))
    except Exception as e:
        atributos.append({"erro": str(e)})

lpu_attrs = pd.concat([lpu, pd.DataFrame(atributos)], axis=1)
lpu_attrs.to_parquet("lpu_atributos.parquet", index=False)
print(f"Concluído: {len(lpu_attrs)} itens processados → lpu_atributos.parquet")
