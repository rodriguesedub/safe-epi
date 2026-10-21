# SAFEEPI, MVP

Conferência de EPIs na pré-liberação segura da atividade. O colaborador pede a liberação; o sistema cruza os EPIs que a atividade exige com os EPIs entregues a ele e sinaliza o que está vencido, com CA expirado, avariado, extraviado ou não entregue. O **técnico de segurança** confere fisicamente no local e colhe duas assinaturas (a dele e a ciência do colaborador). Quando a atividade exige, a **gestora de SST** aprova, e quem conferiu não pode aprovar. A decisão fica num registro imutável, com hash SHA-256.

Django 5.2 + HTMX + SQLite (ou PostgreSQL), pronto para rodar no seu computador e ser apresentado.

## Como rodar

Você precisa do **Python 3.10 ou superior** ([python.org/downloads](https://www.python.org/downloads/)). No Windows, marque **"Add python.exe to PATH"** durante a instalação. Não precisa de Docker, banco de dados nem internet depois da primeira instalação.

**Windows:** dê dois cliques em `iniciar.bat`.

**macOS ou Linux:** no terminal, dentro da pasta do projeto:

```bash
./iniciar.sh
```

Na primeira vez o script cria um ambiente virtual (`.venv`), instala o Django, cria o banco `db.sqlite3` e carrega os dados de demonstração. Depois sobe o servidor em **http://127.0.0.1:8000**. Para parar, feche a janela ou pressione Ctrl+C.

Se você já tinha uma versão anterior rodando, rode `resetar_demo.bat` (ou `./resetar_demo.sh`) uma vez: os dados antigos não têm o técnico de segurança.

### Usuários de demonstração

Senha de todos: **safeepi123**

| Usuário | Pessoa | Perfil | O que faz |
| --- | --- | --- | --- |
| `operador` | João Pereira | Colaborador | Pede a liberação, vê os próprios EPIs com CA, pede troca, assina a ciência |
| `tecnico` | Rodrigo Teixeira | Técnico de segurança | Confere os EPIs no local, responde o checklist, colhe as duas assinaturas |
| `almox` | Paulo Mendes | Almoxarifado | Entrega EPI com assinatura, atende a fila de reposição, estoque, importação |
| `gestor` | Mariana Costa | Gestora de SST | Aprova ou bloqueia, painel, estatísticas de EPI, busca, alertas, relatório, auditoria |
| `operador2` | Ana Souza | Colaboradora | Tem uma pré-liberação NR-10 aguardando aprovação |
| `admin` | | Administrador | Tudo, inclusive cadastros completos no Django Admin |

Durante a apresentação, use o botão **Demonstração**, no canto inferior esquerdo, para trocar de pessoa com um clique.

## Tutorial animado

Na tela de login, em **Ver como funciona**, ou no botão **Demonstração**, há duas opções. As duas voltam os dados ao início e contam a mesma história em 4 cenas: João pede a liberação de um trabalho em altura, o talabarte vencido é barrado e trocado pelo Paulo, o Rodrigo confere no local e a Mariana aprova. No fim, as estatísticas de EPI.

- **Tutorial guiado:** um balão aponta cada passo e espera você agir no elemento destacado. Se preferir, o botão **Fazer por mim** executa o passo.
- **Reprodução automática:** um cursor faz tudo sozinho, do pedido à aprovação, em cerca de 4 minutos. Serve para apresentar sem tocar no computador e para gravar.

Quem trabalha em campo (colaborador e técnico) aparece dentro de uma moldura de celular; a gestora e o almoxarifado, no computador. Teclas: **Espaço** pausa, **→** avança, **Esc** sai.

## Gravar o vídeo

**Gravando você mesmo.** Abra o sistema, deixe o navegador em tela cheia (F11) e clique em **Reprodução automática**. Há uma contagem de 3 segundos para você começar a gravar. O ponteiro do mouse some enquanto você não mexe nele. Para gravar a tela: no Windows, Win+Alt+R (Xbox Game Bar) ou OBS; no macOS, Cmd+Shift+5.

**Sem gravar nada.** Dê dois cliques em `gravar_video.bat` (macOS ou Linux: `./gravar_video.sh`). Na primeira vez ele instala o gravador (Playwright, Chromium e ffmpeg, uns 200 MB). Depois abre um navegador invisível, roda a reprodução automática e salva **`videos/safeepi-tutorial.mp4`** em Full HD. Seus dados não mudam: a gravação usa um banco separado.

Opções: `gravar_video.bat --velocidade 1.25` (mais curto), `--720` (arquivo menor), `--ver` (mostra a janela enquanto grava).

O roteiro da história está em `static/js/tour-passos.js`, com os textos dos balões; dá para mudar as falas sem mexer no resto.

## Antes de cada apresentação

Recrie os dados para que os horários fiquem "de agora" (a pré-liberação da Ana, por exemplo, aparece como conferida há poucos minutos):

- Windows: dois cliques em `resetar_demo.bat`
- macOS/Linux: `./resetar_demo.sh`

O tutorial já faz isso sozinho quando começa.

### Abrir no celular (opcional)

Com o celular na mesma rede Wi-Fi, rode `./iniciar.sh 0.0.0.0:8000` (ou, no Windows, `.venv\Scripts\python.exe manage.py runserver 0.0.0.0:8000`) e acesse `http://IP-DO-COMPUTADOR:8000` no celular. O Windows pode pedir para liberar o firewall. A instalação como app (PWA) só funciona em `localhost` ou com HTTPS; pelo IP da rede o sistema funciona normalmente no navegador.

## Roteiro de apresentação ao vivo (cerca de 7 minutos)

Se preferir conduzir sem o tutorial, troque de pessoa pelo botão **Demonstração**.

1. **O pedido (João, colaborador).** Na tela inicial, os EPIs dele com o CA e a validade: o talabarte venceu. Clique em **Solicitar liberação**, escolha **Trabalho em altura (NR-35)**, informe o local e envie. O João não marca nenhum EPI: quem confere é o técnico.
2. **O sistema barra.** O talabarte aparece vencido. O João toca em **Pedir troca ao almoxarifado**.
3. **A troca (Paulo, almoxarifado).** O pedido está no topo da fila, com "colaborador aguardando no local". **Atender**, escolher a unidade (só aparecem unidades válidas, com CA vigente), assinatura do João, **Registrar entrega**. O talabarte vencido sai de uso.
4. **A conferência (Rodrigo, técnico de segurança).** O pedido do João está em **Conferências**. Marque **Conforme** em cada EPI e **Sim** no checklist, confirme a conferência física e colha as duas assinaturas: a do técnico e a ciência do João. Como é trabalho em altura, segue para aprovação.
5. **A decisão (Mariana, gestora de SST).** No painel, o pedido mostra quem conferiu. Abra, revise, assine e **Libere**. Mostre o **registro imutável** (hash SHA-256, integridade verificada) e o **comprovante para imprimir**. Se a Mariana tivesse conferido, o sistema não deixaria ela aprovar.
6. **Estatísticas de EPI (Mariana).** Quantos EPIs há em uso, em estoque e fora de uso; **quem mais danifica**; **quem mais perde**; **quem está com EPI fora da validade**; e quanto há de cada EPI, com o CA (o respirador PFF2 aparece com CA vencido).
7. **Ficha de EPI (NR-6).** Em **Colaboradores**, abra o João e clique em **Ficha de EPI**: o registro de fornecimento com data, CA, unidade e assinatura, pronto para imprimir.
8. **Maturidade.** A **Inspeção de rotina (NR-6)** está em modo registro: conferência 100% conforme libera na hora, sem esperar a gestora.

Pontos para comentar: o sistema nunca libera sem uma pessoa confirmar a conferência física; quem confere não aprova; o colaborador não confere os próprios EPIs; registros decididos não podem ser alterados, nem pelo admin.

## O que mudou nesta versão

Pedidos do professor na última apresentação:

- **Segregação de funções.** O colaborador não dá mais o ok nos próprios EPIs. Ele pede a liberação e assina a ciência; a conferência física é do técnico de segurança; a aprovação é de outra pessoa.
- **Estatísticas de EPI para o gestor.** Quanto há de cada EPI, quem mais danifica, quem mais perde, quem está com EPI fora da validade e ocorrências por colaborador, por período (30, 90 e 180 dias). Perda agora marca a unidade como extraviada.
- **CA em todas as telas.** Do celular do colaborador ao relatório, cada EPI aparece com o número do CA; CA vencido fica marcado.
- **Ficha de EPI (NR-6)** por colaborador, para imprimir.
- **Visual mais minimalista.** Branco, tinta e linhas finas; cor só onde tem significado (azul ação, verde ok, âmbar atenção, vermelho bloqueio).
- **Tutorial animado** e **gravador de vídeo**.

## O que está implementado

| Funcionalidade | Onde ver |
| --- | --- |
| F01 Autenticação e perfis | Login; cada perfil tem menu e permissões próprios |
| F02 Cadastros base | **Cadastros** (Django Admin) para gestor, almoxarifado e admin |
| F03 Matriz atividade × EPI | Admin, em Atividades (EPIs obrigatórios e perguntas do checklist) |
| F04 Entrega com assinatura | **Entregar EPI** |
| F05 Checklist com validação automática | Pré-liberação em conferência (técnico de segurança) |
| F06 Decisão liberar/bloquear | Pré-liberação aguardando aprovação (gestora, nunca quem conferiu) |
| F07 Alertas de validade | **Alertas** e comando `gerar_alertas` (o e-mail aparece no terminal) |
| F08 Busca centralizada | **Colaboradores** |
| F09 Trilha de auditoria | **Trilha de auditoria** e no fim de cada pré-liberação |
| F10 Reposição digital | Pedido de troca na conferência e **Reposições** (almoxarifado) |
| F11 Relatório de conformidade | **Relatório de conformidade** (tela para imprimir e CSV) |
| F12 Painel de KPIs | **Painel** |
| F13 Avaria com foto | Conferência (Danificado + foto) e Meus EPIs |
| F14 Importação CSV | **Importar planilha** (exemplos em `dados_exemplo/`) |
| F15 Rigor configurável | Campo "exige aprovação" da atividade |
| Estatísticas de EPI | **Estatísticas** (gestora) |
| Ficha de EPI (NR-6) | Página do colaborador |
| Tutorial e gravação | Login, botão **Demonstração**, `gravar_video.bat` |
| PWA | `manifest.webmanifest`, `sw.js` e página offline |
| API mínima para o QR da fase 2 | `GET /api/v1/epis/<código>/` |

Fica para a fase 2, como na especificação: leitura de QR Code, RFID/NFC, modo offline completo, integração com almoxarifado/ERP, visão computacional e multiempresa. O código de cada EPI (ex.: `EPI-000123-7`, com dígito verificador) já é o conteúdo que o QR vai carregar.

## Para o time

```bash
.venv/bin/python manage.py test          # 40 testes (Windows: .venv\Scripts\python.exe manage.py test)
.venv/bin/python manage.py gerar_alertas # roda o job diário de alertas
.venv/bin/python manage.py seed_demo --reset
```

Organização (monolito modular, decisão D1): um app Django por domínio: `contas`, `cadastros`, `epis`, `liberacoes`, `alertas`, `reposicao`, `relatorios`, `auditoria` e `core` (layout, PWA, dados de demonstração, tutorial). As regras de negócio ficam em `services.py` de cada app, fora das views, e são o que os testes cobrem. As estatísticas ficam em `relatorios/estatisticas.py`. O tutorial é `static/js/tour.js` (motor) e `static/js/tour-passos.js` (roteiro).

Para usar PostgreSQL em vez de SQLite, instale `requirements-postgres.txt` e defina `DATABASE_URL=postgres://usuario:senha@host:5432/banco`.

Os dados de demonstração são fictícios, inclusive os números de CA. Configurações por variável de ambiente: `SAFEEPI_DEBUG`, `SAFEEPI_SECRET_KEY`, `SAFEEPI_DEMO` (liga a troca de usuário e o tutorial), `SAFEEPI_ALLOWED_HOSTS` e `SAFEEPI_SQLITE` (outro arquivo de banco). Esta configuração é para demonstração local; para publicar, desligue o modo demo e o DEBUG e troque a chave secreta.
