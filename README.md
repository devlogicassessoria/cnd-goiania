# Robô CND Mobiliária – Prefeitura de Goiânia

Emite em lote a **Certidão Conjunta de Débitos Mobiliários (CAE)** da Prefeitura de Goiânia,
salva em PDF, lê a certidão e separa em pastas.

## ⚡ Uso rápido (Windows) – só baixar e executar
1. Baixe o repositório: botão **Code → Download ZIP** no GitHub (e extraia) ou `git clone`.
2. Tenha o **Google Chrome** instalado.
3. Dê dois cliques em **`CND_Goiania.exe`** (na raiz). O `config.json` ao lado dele é lido automaticamente.
4. Para atualizar: baixe o ZIP de novo ou `git pull`.

> Windows SmartScreen pode avisar na 1ª vez (o .exe não é assinado): "Mais informações" → "Executar assim mesmo".

## 1. Gerar o .exe (uma vez, no Windows)
1. Instale o **Python 3.10+** (marque "Add Python to PATH") e tenha o **Google Chrome**.
2. Dê dois cliques em `build_exe.bat`.
3. O programa sai em `dist\CND_Goiania.exe` + `dist\config.json`. Copie os dois juntos para onde quiser.

> Sem gerar o .exe: `rodar_sem_exe.bat` abre a mesma interface direto pelo Python.

## 1b. Linux
- `./rodar_linux.sh` – abre a interface direto pelo Python (cria `.venv-linux`; se faltar o
  `python3-tk`, baixa um Python completo com o `uv`, sem sudo). Não precisa ter Chrome instalado:
  o Selenium baixa o "Chrome for Testing" na primeira vez.
- `./build_linux.sh` – gera o executável Linux `dist/linux/CND_Goiania` (+ `config.json`).
- `./build_exe_no_linux.sh` – gera o **.exe do Windows a partir do Linux** via Docker + Wine
  (imagem `tobix/pywine:3.12`) → `dist/windows/CND_Goiania.exe`.
  Alternativa: subir no GitHub e rodar o workflow `.github/workflows/build-exe.yml`.

## 2. Usar
1. Abra `CND_Goiania.exe`.
2. Escolha a planilha (modelo: `modelo_planilha.xlsx`) e a pasta de saída.
3. Clique **Iniciar** e acompanhe na tabela, nos contadores e no log.
   Duplo clique numa linha abre a certidão salva.

Planilha: precisa de uma coluna **CNPJ**; a coluna **IM** (ou "Inscrição Municipal"/"CAE") é
opcional por linha; **Razão Social** é opcional (entra no nome do arquivo).
Aceita direto o **CONTROLE DE LICENÇAS** (1ª coluna sem título = nome; usa só CNPJ e INSCRIÇÃO MUNICIPAL).
Com a coluna **MUNICIPIO**, só processa as linhas de `config.json > filtro_municipio` (padrão `"GOIANIA"`,
comparação exata sem acento; deixe `""` para processar todas).

## 3. O que o robô faz
- **Com IM** → Certidões > Débitos Mobiliários > Conjunta de Débitos Mobiliários > Inscrição CAE + "." > Emitir.
- **Sem IM** → Situação do Contribuinte pelo CNPJ (sem pontuação) + "." > pega a IM > emite como acima.
- Salva o PDF, lê o texto e move para:
```
Saída\
 ├─ Com Pendencia\Positiva   Com Pendencia\Negativa
 ├─ Sem Pendencia\Positiva   Sem Pendencia\Negativa
 ├─ _Nao Classificadas       (texto não reconhecido – conferir manualmente)
 ├─ _Consultas Contribuinte  (PDF da consulta de IM pelo CNPJ)
 └─ Relatorio CND <data>.xlsx
```
- Se o site recusar o ".", abre uma janelinha com a imagem para você digitar (ou pular a empresa).

## 3b. Controle de requisições (ritmo de acesso ao site)
Para não sobrecarregar o sistema da Prefeitura nem ser bloqueado por excesso de acessos, cada
consulta passa por `config.json > controle_requisicoes`:
| Chave | Padrão | O que faz |
|---|---|---|
| `intervalo_min_segundos` / `intervalo_max_segundos` | 6 / 15 | espera aleatória entre consultas |
| `pausa_longa_a_cada` | 25 | a cada N consultas faz uma pausa longa (60–150 s) |
| `maximo_por_hora` | 120 | teto de consultas por hora (0 = sem teto) |
| `espera_apos_erro_segundos` | 20 | espera crescente (20, 40, 80… até 300 s) quando o site falha |
| `erros_seguidos_para_resfriar` / `resfriamento_segundos` | 3 / 600 | após 3 falhas seguidas, pausa de 10 min |

Com o padrão, 215 empresas levam cerca de 1h30–2h. Para ir mais rápido, reduza os intervalos.

## 4. Regra de classificação (editável no `config.json`)
| Texto da certidão | Tipo | Pendência |
|---|---|---|
| "Certidão Negativa" | Negativa | Sem (a menos que cite pendência) |
| "Positiva com efeito de negativa" | Negativa | **Com** (débitos parcelados/suspensos) |
| "Certidão Positiva" | Positiva | Com, se citar pendência/débitos |

Mude as listas `palavras_*`, `efeito_negativa_vai_para` e `efeito_negativa_conta_como_pendencia`
no bloco `classificacao` do `config.json` – não precisa regerar o .exe.

## 5. Claude Code
- Skill: `.claude/skills/cnd-goiania/SKILL.md`
- Agente: `.claude/agents/cnd-goiania-robo.md` (chame com "use o agente cnd-goiania-robo para ...")
