# Lab04S01 — Sistema de Moeda Estudantil

Esta entrega aplica o escopo da sprint informado na solicitação ao projeto deste repositório. O PDF anexado descreve o DevMatch, outro sistema; os casos de uso aqui seguem a modelagem da release anterior em [`README.md`](../../README.md), especialmente UC01–UC13.

## Diagramas UML

Os arquivos `.puml` são editáveis em ferramentas compatíveis com PlantUML; os `.svg` são as versões vetoriais prontas para leitura e inclusão no relatório.

| Fluxo | Casos de uso | Diagrama |
| --- | --- | --- |
| Instituições | UC04 | [Sequência](00_instituicoes.svg) · [Fonte](00_instituicoes.puml) |
| Cadastros | UC01, UC02, UC05 | [Sequência](01_cadastros.svg) · [Fonte](01_cadastros.puml) |
| Autenticação | UC03 | [Sequência](02_autenticacao.svg) · [Fonte](02_autenticacao.puml) |
| Crédito semestral | UC06 | [Sequência](03_credito_semestral.svg) · [Fonte](03_credito_semestral.puml) |
| Distribuição e aviso | UC07, UC13 | [Sequência](04_distribuicao.svg) · [Fonte](04_distribuicao.puml) |
| Saldo e extrato | UC08 | [Sequência](05_extrato.svg) · [Fonte](05_extrato.puml) |
| Vantagens e catálogo | UC09, UC10 | [Sequência](06_vantagens.svg) · [Fonte](06_vantagens.puml) |
| Resgate, cupom e aviso | UC11, UC12, UC13 | [Sequência](07_resgate.svg) · [Fonte](07_resgate.puml) |
| Fluxo integrado | UC01–UC13 | [Visão geral de interação](08_visao_geral_interacao.svg) · [Fonte](08_visao_geral_interacao.puml) |

O diagrama de visão geral usa a notação de fluxo de controle UML e nós `ref` para indicar os usos de interação detalhados nos diagramas de sequência. O crédito semestral aparece como gatilho independente do acesso web.

## Casos de uso implementados nesta sprint

| Caso | Implementação |
| --- | --- |
| UC05 | Pré-cadastro de professor por administrador, vínculo com instituição, credenciais e conta de moedas. UC04 já era mantido no Django Admin. |
| UC06 | Comando `creditar_semestre`, crédito acumulativo de 1.000 moedas por professor ativo e unicidade por semestre. |
| UC07 | Distribuição com valor positivo, motivo obrigatório, débito condicional e crédito atômico. |
| UC08 | Extrato próprio de aluno ou professor, com saldo e transações em ordem decrescente. |
| UC09 | Cadastro e edição de vantagem pela empresa proprietária, com descrição, URL de foto, custo positivo e estado ativo. |
| UC10 | Catálogo de vantagens ativas para alunos. |
| UC11–UC12 | Resgate com débito atômico, custo histórico e código de cupom único. |
| UC13 | Notificações persistidas para o aluno (distribuição) e para aluno e empresa (resgate), enviadas após commit; falhas podem ser reenviadas. |

## Executar

```bash
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
python manage.py test
```

O administrador pré-cadastra professores em `/professores/novo/`. Professores e alunos têm acesso ao próprio saldo e extrato; professores distribuem moedas em `/distribuir/`. Empresas mantêm vantagens em `/minhas-vantagens/`; alunos consultam o catálogo em `/vantagens/` e confirmam o resgate por POST.

O crédito é executado por `python manage.py creditar_semestre 2026.2`. Sem argumento, o comando usa o semestre da data local. Para execução automática, agende esse comando no início de janeiro e julho; reexecutá-lo no mesmo semestre não duplica créditos. Exemplo de cron, ajustando os caminhos ao ambiente:

```cron
0 0 1 1,7 * cd /caminho/do/projeto && /caminho/do/python manage.py creditar_semestre
```

Por padrão, o backend de e-mail imprime mensagens no console para desenvolvimento. Para entrega real, configure `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` e `DEFAULT_FROM_EMAIL`. Após corrigir uma falha de envio, execute `python manage.py reenviar_emails`.

## Regerar os diagramas

```bash
plantuml -tsvg docs/lab04s01/*.puml
```

## Verificação

Os testes cobrem pré-cadastro restrito, idempotência do crédito, saldos e rollback, notificações, reenvio, autorização por perfil, cupom e resgate por POST. Os arquivos SVG foram gerados a partir das fontes PlantUML e verificados visualmente.
