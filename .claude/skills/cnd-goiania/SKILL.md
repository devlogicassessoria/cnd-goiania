---
name: cnd-goiania
description: Emissão em lote da Certidão Negativa de Débitos Mobiliários (CND/CAE) da Prefeitura de Goiânia com Selenium — lê planilha CNPJ+IM, consulta IM pelo CNPJ quando falta, salva o PDF, lê a certidão e separa em pastas Com/Sem Pendência > Positiva/Negativa. Use para rodar, ajustar, depurar ou gerar o .exe do robô CND Goiânia.
---

# Robô CND Mobiliária – Prefeitura de Goiânia

Projeto Python (Selenium + Tkinter) que roda local no Windows como `CND_Goiania.exe`.

## Estrutura do projeto

| Arquivo | Papel |
|---|---|
| `app.py` | Interface Tkinter (acompanhamento) e modo linha de comando |
| `robo/planilha.py` | Lê .xlsx/.csv; acha colunas CNPJ, IM (Inscrição Municipal/CAE) e Razão Social pelo cabeçalho |
| `robo/navegador.py` | Selenium: navegação nos frames do site, preenchimento, "." na verificação, PDF |
| `robo/classificador.py` | Lê o texto do PDF e decide a pasta |
| `robo/processo.py` | Orquestra tudo, tentativas, relatório Excel |
| `config.json` | URLs, texto da verificação, timeouts e **palavras-chave de classificação** |
| `build_exe.bat` | Gera `dist/CND_Goiania.exe` com PyInstaller |
| `tests/test_basico.py` | Testes offline (planilha, classificação, extração de IM) |

## Fluxo de negócio (não alterar sem pedido do usuário)

1. Ler a planilha. Para cada linha:
2. **Tem IM?** → abrir `menu_certidoes` → link **Débitos Mobiliários** → **Conjunta de Débitos Mobiliários - Regularidade Fiscal** → campo **Inscrição CAE** = IM → campo de verificação = `"."` → **Emitir Certidão**.
3. **Não tem IM?** → abrir `situacao_contribuinte` → campo **Número do CNPJ/CPF** = CNPJ só com dígitos → verificação `"."` → **Consulta** → extrair a(s) Inscrição(ões) Municipal(is) da resposta → seguir o passo 2 para cada uma. O PDF da consulta fica em `_Consultas Contribuinte/`.
4. Salvar a certidão em PDF (Chrome `Page.printToPDF`, isolando só o frame da certidão).
5. Ler o PDF (pypdf) e mover para:
   ```
   <saída>/Com Pendencia/Positiva    <saída>/Com Pendencia/Negativa
   <saída>/Sem Pendencia/Positiva    <saída>/Sem Pendencia/Negativa
   <saída>/_Nao Classificadas
   ```
6. Gerar `Relatorio CND <data>.xlsx` na pasta de saída.

Se o "." for recusado e a opção estiver ligada, a interface mostra a imagem de verificação e o usuário digita. **Nunca** implementar quebra automática de captcha (OCR, serviços de resolução etc.).

## Detalhes do site (levantados em 26/11/2026)

- `https://www.goiania.go.gov.br/sistemas/saces/asp/saces00000f0.asp?sigla=sccer` é um **frameset**; o menu real é `/sistemas/sccer/asp/sccer00000f0.asp`, e os links chamam `javascript:carrega('/sistemas/sccer/asp/sccer00100f0.asp',1)` (Débitos Mobiliários) e `carrega('/sistemas/sccer/asp/sccer00101f0.asp',2)` (Conjunta).
- Formulário da CND (`sccer00101f0.asp`): input texto ao lado de "Inscrição CAE", imagem de verificação + link "Trocar caracteres", input de verificação, botão "Emitir Certidão". Plano B = abrir essa URL direto (`cnd_mobiliario_direto`).
- Situação do Contribuinte (`sccae00010r0.asp`): inputs "Número do CNPJ/CPF", "Nº da Inscrição Municipal", verificação (imagem `/sistemas/saces/asp/geral00005p0.asp`), botão "Consulta".
- Páginas ASP em latin-1; os XPaths usam trechos sem acento (`'bitos Mobili'`, `'Inscri'`) para não depender de encoding.
- Certidão emitida (texto real): título "CERTIDÃO DE REGULARIDADE FISCAL MOBILIÁRIA" + "NEGATIVA DE DÉBITOS MOBILIÁRIOS" ("NÃO CONSTA DÉBITO VENCIDO OU A VENCER") ou "POSITIVA DE DÉBITOS MOBILIÁRIOS" ("CONSTAM DÉBITOS VENCIDOS"). Testes em `tests/test_basico.py`.
- `RoboCND.procurar()` percorre todos os frames recursivamente e deixa o driver dentro do frame achado.

## Como ajustar

- **Classificação errada** → editar só `config.json > classificacao` (texto comparado sem acento e em maiúsculas). Depois rodar `python -m pytest tests -q` e adicionar um teste com o trecho real da certidão.
- **Site mudou** → ajustar as constantes `XP_*` e `MARCADORES_CERTIDAO` no topo de `robo/navegador.py`. Para inspecionar: abrir as URLs acima num navegador e ver o snapshot/HTML.
- **Planilha com cabeçalho diferente** → acrescentar o nome em `ALIAS_CNPJ`, `ALIAS_IM` ou `ALIAS_NOME` em `robo/planilha.py`.

## Rodar e empacotar

```bat
rodar_sem_exe.bat                 :: roda direto com Python
build_exe.bat                     :: gera dist\CND_Goiania.exe + dist\config.json
python app.py planilha.xlsx C:\saida --headless   :: sem interface
```
O .exe precisa ser gerado **no Windows** (PyInstaller não faz cross-compile). Requer Google Chrome instalado; o Selenium Manager baixa o chromedriver certo na primeira execução (precisa de internet liberada para `googlechromelabs.github.io` / `storage.googleapis.com`). Se a rede bloquear, baixar o chromedriver manualmente e informar o caminho em `config.json > chromedriver_caminho`.

## Checklist antes de entregar alteração

1. `python -m pytest tests -q` passa.
2. `python -m pyflakes app.py robo` sem erros.
3. Testar com 2–3 empresas reais (uma com IM, uma sem IM) com o Chrome visível.
4. Regerar o .exe com `build_exe.bat`.
