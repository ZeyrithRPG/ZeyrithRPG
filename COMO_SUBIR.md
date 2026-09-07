# Como colocar o bot no ar — passo a passo

Você não precisa instalar nada no seu computador. É tudo feito em site, copiando e colando.
Isso é feito só 1 vez. Depois, o bot fica rodando sozinho pra sempre.

## Passo 1 — Criar o bot no Telegram

1. Abra o Telegram e procure por `@BotFather`.
2. Mande `/newbot`.
3. Escolha um nome (ex: "A Infecção que Segura o Mundo") e um usuário terminado em "bot" (ex: `infeccao_rpg_bot`).
4. Ele te devolve um **Token** — uma sequência tipo `123456:ABC-def...`. Guarde essa linha num bloco de notas, é a chave do seu bot.

## Passo 2 — Criar o banco de dados permanente (Neon)

1. Vá em [neon.tech](https://neon.tech) e crie uma conta grátis (sem cartão).
2. Crie um novo projeto — pode chamar de "infeccao-rpg".
3. Na tela do projeto, procure o botão **"Connection String"** — copia a linha que começa com `postgresql://...` e guarda no mesmo bloco de notas. É a chave do banco de dados.

## Passo 3 — Subir o código pro GitHub

1. Crie uma conta grátis em [github.com](https://github.com), se ainda não tiver.
2. Clique em **"New repository"**. Dê um nome (ex: `infeccao-rpg-bot`). Pode deixar privado.
3. Na tela do repositório vazio, clique em **"uploading an existing file"**.
4. Arraste TODOS os arquivos e pastas que estão dentro do zip que te mandei (solta tudo de uma vez na página).
5. Clique em **"Commit changes"** lá embaixo.

Pronto — seu código está no ar, mesmo sem estar rodando ainda.

## Passo 4 — Colocar o bot pra rodar no Render

1. Vá em [render.com](https://render.com) e crie conta grátis (dá pra entrar direto com o GitHub).
2. Clique em **"New +" → "Web Service"**.
3. Escolha o repositório que você criou no Passo 3.
4. Preenche assim:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
   - **Plan:** Free
5. Desce até **"Environment Variables"** e clica em **"Add Environment Variable"** duas vezes:
   - Nome `TELEGRAM_BOT_TOKEN` → valor: cola o token do Passo 1
   - Nome `DATABASE_URL` → valor: cola a connection string do Neon (Passo 2)
6. Clique em **"Create Web Service"**.

O Render vai instalar tudo, ligar o bot, e **na primeira vez que ele ligar, ele importa os dados do jogo sozinho** (as 14 tiers, 308 armas, 123 monstros — tudo já vem pronto dentro do código, você não precisa fazer nada disso na mão). Leva uns 2-3 minutos.

## Passo 5 — Testar

Abra o Telegram, procure pelo nome de usuário do bot que você criou no Passo 1, e manda `/start`.

---

### Se algo der errado
No painel do Render, tem uma aba **"Logs"** — mostra exatamente o que aconteceu. Se travar em algum passo, me manda o texto que aparece lá que eu leio pra você e te digo o que fazer.
