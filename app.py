from flask import Flask, jsonify, request, render_template, url_for, redirect, session, flash
import sqlite3
from flask_bcrypt import Bcrypt
from datetime import datetime
from functools import wraps
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from pathlib import Path
import uuid


app = Flask(__name__)
DATABASE = 'database.db'
app.secret_key = 'your_secret_key'
bcrypt = Bcrypt(app)


app.config['UPLOAD_FOLDER'] = Path(app.root_path) / 'static' / 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024


ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
app.config['UPLOAD_FOLDER'].mkdir(parents=True, exist_ok=True)


def extensao_permitida(nome_arquivo):
    return '.' in nome_arquivo and nome_arquivo.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def salvar_imagem(arquivo, prefixo='imagem'):
    """Salva a imagem em static/uploads e retorna o caminho relativo usado pelo url_for('static')."""
    if not arquivo or not arquivo.filename:
        return None

    nome_original = secure_filename(arquivo.filename)
    if not extensao_permitida(nome_original):
        raise ValueError(
            'Formato de imagem não permitido. Use PNG, JPG, JPEG, GIF ou WEBP.')

    extensao = nome_original.rsplit('.', 1)[1].lower()
    nome = f'{prefixo}_{uuid.uuid4().hex}.{extensao}'
    arquivo.save(app.config['UPLOAD_FOLDER'] / nome)
    return f'uploads/{nome}'


def excluir_imagem(caminho):
    """Remove apenas arquivos armazenados em static/uploads."""
    if not caminho or not caminho.startswith('uploads/'):
        return
    arquivo = Path(app.root_path) / 'static' / caminho
    if arquivo.exists() and arquivo.is_file():
        arquivo.unlink()


def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS livros(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                autor TEXT NOT NULL,
                genero TEXT NOT NULL,
                lancado INTEGER NOT NULL,
                imagem TEXT 
            )
        '''),

        conn.execute('''
            CREATE TABLE IF NOT EXISTS usuarios(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                senha TEXT NOT NULL,
                perfil TEXT NOT NULL DEFAULT 'usuario',
                imagem TEXT 
            )
        '''),

        conn.execute('''
                CREATE TABLE IF NOT EXISTS emprestimos(
                     id INTEGER PRIMARY KEY AUTOINCREMENT,
                     usuario_id INTEGER NOT NULL,
                     livro_id INTEGER NOT NULL,
                     data_emprestimo TEXT,
                     devolver INTEGER DEFAULT 0,
                     FOREIGN KEY(usuario_id) REFERENCES usuarios(id),
                     FOREIGN KEY(livro_id) REFERENCES livros(id)
        )
        ''')

        cursor = conn.cursor()
        cursor.execute('''SELECT COUNT(*) FROM usuarios''')
        total_usuarios = cursor.fetchone()[0]

        if total_usuarios == 0:
            senha_usermax = bcrypt.generate_password_hash(
                'max123').decode('utf-8')
            cursor.execute('INSERT INTO usuarios (nome, senha, perfil) VALUES (?, ?, ?)',
                           ('usermax', senha_usermax, 'max'))

        conn.commit()
        print("\n ---- BIBLIOTECA ABERTA ---- ")

# ---conexao com o banco de dados---#


def conexao():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

# ---verifica se o usuario está logado---#


def usuario_logado():
    return 'usuario_id' in session


def administrador():
    return session.get('perfil') in ('admin', 'max')


def usuario_max():
    return session.get('perfil') == 'max'


def login_necessario(func):
    @wraps(func)
    def verificar_login(*args, **kwargs):
        if not usuario_logado():
            flash('Você precisa estar logado para acessar essa página')
            return redirect(url_for('login'))

        return func(*args, **kwargs)
    return verificar_login


def existe_outro_max(usuario_id):
    conn = conexao()
    cursor = conn.execute(
        "SELECT COUNT(*) FROM usuarios WHERE perfil='max' AND id != ?", (usuario_id,))
    count = cursor.fetchone()[0]
    conn.close()
    return count > 0


# ---livros---#
@app.route('/livros', methods=['GET'])
@login_necessario
def livros():
    conn = conexao()
    livros = conn.execute('SELECT * FROM livros')
    return render_template('admin/livros.html', livros=livros)


# ---buscar livros---#
@app.route('/buscar_livros', methods=['GET'])
@login_necessario
def buscar_livros():
    query = request.args.get('query', '').strip()
    conn = conexao()
    livros = conn.execute('SELECT * FROM livros')

    if query:
        livros = conn.execute(
            'SELECT * FROM livros WHERE titulo LIKE ? OR autor LIKE ? OR genero LIKE ?',
            (f'%{query}%', f'%{query}%', f'%{query}%')
        ).fetchall()

        if not livros:
            flash('Nenhum livro encontrado para a busca realizada.', 'warning')

    return render_template('admin/livros.html', livros=livros)


# --- listar empréstimos (para usuários e admins) ---#
@app.route('/emprestimos', methods=['GET'])
@login_necessario
def listar_emprestimos():
    conn = conexao()
    if administrador():

        emprestimos = conn.execute('''
            SELECT e.id, u.nome AS usuario, l.titulo AS livro, e.data_emprestimo, e.devolver
            FROM emprestimos e
            JOIN usuarios u ON e.usuario_id = u.id
            JOIN livros l ON e.livro_id = l.id
        ''').fetchall()
    else:

        emprestimos = conn.execute('''
            SELECT e.id, u.nome AS usuario, l.titulo AS livro, e.data_emprestimo, e.devolver
            FROM emprestimos e
            JOIN usuarios u ON e.usuario_id = u.id
            JOIN livros l ON e.livro_id = l.id
            WHERE e.usuario_id = ?
        ''', (session['usuario_id'],)).fetchall()

    conn.close()
    return render_template('admin/emprestimos.html', emprestimos=emprestimos)


# --- realizar um empréstimo ---#
@app.route('/emprestimos/novo/<int:livro_id>', methods=['POST'])
@login_necessario
def novo_emprestimo(livro_id):
    usuario_id = session['usuario_id']
    data_atual = datetime.now().strftime('%d/%m/%Y %H:%M')

    conn = conexao()
    try:
        emprestado = conn.execute(
            "SELECT * FROM emprestimos WHERE livro_id = ? AND devolver = 0",
            (livro_id,)
        ).fetchone()

        if emprestado:
            flash('Este livro já está emprestado no momento.', 'warning')
        else:
            conn.execute(
                "INSERT INTO emprestimos (usuario_id, livro_id, data_emprestimo, devolver) VALUES (?, ?, ?, 0)",
                (usuario_id, livro_id, data_atual)
            )
            conn.commit()
            flash('Livro emprestado com sucesso!', 'success')

    finally:
        conn.close()

    return redirect(url_for('livros'))


# --- devolver um livro ---#
@app.route('/emprestimos/devolver/<int:id>', methods=['POST'])
@login_necessario
def devolver_emprestimo(id):
    conn = conexao()
    try:
        conn.execute("UPDATE emprestimos SET devolver = 1 WHERE id = ?", (id,))
        conn.commit()
        flash('Livro devolvido com sucesso!', 'success')
    finally:
        conn.close()

    return redirect(url_for('listar_emprestimos'))


@app.route('/pedir_livro/<int:livro_id>', methods=['POST'])
@login_necessario
def pedir_livro(livro_id):
    usuario_id = session['usuario_id']
    data_atual = datetime.now().strftime('%d/%m/%Y %H:%M')

    conn = conexao()
    try:

        conn.execute(
            "INSERT INTO emprestimos (usuario_id, livro_id, data_emprestimo, devolver) VALUES (?, ?, ?, 0)",
            (usuario_id, livro_id, data_atual)
        )
        conn.commit()
        flash('Pedido de empréstimo realizado com sucesso!', 'success')
    except Exception as e:
        flash('Erro ao solicitar o livro.', 'danger')
    finally:
        conn.close()

    return redirect(url_for('livros'))


# ---adicionar livro---#
@app.route('/add_livro', methods=['GET', 'POST'])
@login_necessario
def add_livro():
    if not administrador():
        flash('Você precisa ser um adminstrador para acessar essa página')
        return redirect(url_for('livros'))

    if request.method == 'POST':
        titulo = request.form['titulo']
        autor = request.form['autor']
        genero = request.form['genero']
        lancado = request.form['lancado']
        imagem = request.files['imagem']
        caminho_imagem = salvar_imagem(imagem, 'livro')
        conn = conexao()
        conn.execute(
            'INSERT INTO livros (titulo, genero, autor, lancado, imagem) VALUES (?, ?, ?, ?, ?)', (titulo, genero, autor, lancado, caminho_imagem))
        conn.commit()

        return redirect(url_for('livros'))
    return render_template('admin/add_livro.html')


# ---editar livro---#
@app.route('/edit/<int:id>', methods=['POST', 'GET'])
@login_necessario
def edit(id):
    if not administrador():
        flash('Você precisa ser um adminstrador para acessar essa página')
        return redirect(url_for('livros'))

    if request.method == 'POST':
        titulo = request.form.get('titulo')
        autor = request.form.get('autor')
        genero = request.form.get('genero')
        lancado = request.form.get('lancado')
        imagem = request.files.get('imagem')
        caminho_imagem = salvar_imagem(imagem, 'livro')

        if imagem and caminho_imagem:
            conn = conexao()
            cursor = conn.execute(
                "SELECT imagem FROM livros WHERE id=?", (id,))
            livro = cursor.fetchone()
            if livro and livro['imagem']:
                excluir_imagem(livro['imagem'])

        conn = conexao()
        cursor = conn.execute(
            "UPDATE livros SET titulo=?, autor=?, genero=?, lancado=?, imagem=? WHERE id=?", (
                titulo, autor, genero, lancado, caminho_imagem if imagem else None, id)
        )
        conn.commit()
        return redirect(url_for('livros'))

    conn = conexao()
    livro = conn.execute("SELECT * FROM livros WHERE id = ?", (id,)).fetchone()
    conn.close()

    if livro is None:
        return "Livro não encontrado", 404
    return render_template('admin/edit.html', livro=livro)


# ---deletar livro---#
@app.route('/livros/deletar/<int:id>', methods=['POST'])
@login_necessario
def deletar_livro(id):
    if not administrador():
        flash('Você não tem permissão para acessar essa página')
        return redirect(url_for('menu_principal'))

    if request.method == 'POST':
        conn = conexao()
        cursor = conn.execute("SELECT imagem FROM livros WHERE id=?", (id,))
        livro = cursor.fetchone()

        if livro and livro['imagem']:
            excluir_imagem(livro['imagem'])

        cursor = conn.execute("DELETE FROM livros WHERE id=?", (id,))
    if cursor.rowcount == 0:
        return jsonify({'erro': 'Livro não encontrado'}), 404
    conn.commit()
    return redirect(url_for('livros'))


# ---login do usuario---#

@app.route("/login", methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        senha = request.form.get('senha', '')
        if not nome or not senha:
            return render_template('login.html', erro='Preencha todos os campos.')

        conn = conexao()
        try:
            usuario = conn.execute(
                "SELECT * FROM usuarios WHERE nome=?", (nome,)).fetchone()
            if usuario is None:
                flash('Usuário ou senha incorretos.', 'error')
                return render_template('admin/login.html')

            senha_correta = bcrypt.check_password_hash(usuario['senha'], senha)

            if not senha_correta:
                flash('Usuário ou senha incorretos.', 'error')
                return render_template('admin/login.html')

            session.clear()

            session['usuario'] = usuario['nome']
            session['usuario_id'] = usuario['id']
            session['perfil'] = usuario['perfil']
            return redirect(url_for('menu_principal'))

        finally:
            conn.close()
    return render_template('admin/login.html')


# ---cadastro de usuarios---#
@app.route('/cadastro', methods=['GET', 'POST'])
@login_necessario
def cadastro():
    if not administrador():
        flash('Você não tem permissão para acessar essa página')
        return redirect(url_for('menu_principal'))

    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        senha = request.form.get('senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')
        perfil = request.form.get('perfil', 'usuario')

        if not nome:
            flash('Erro: O nome de usuário é obrigatório.', 'danger')
            return render_template('admin/cadastro.html', nome=nome, perfil=perfil)

        if senha != confirmar_senha:
            flash('Erro: As senhas não coincidem.', 'danger')
            return render_template('admin/cadastro.html', nome=nome, perfil=perfil)

        if len(senha) < 8:
            flash('Erro: A senha deve ter pelo menos 8 caracteres.', 'danger')
            return render_template('admin/cadastro.html', nome=nome, perfil=perfil)

        senha_hash = bcrypt.generate_password_hash(senha).decode('utf-8')

        conn = conexao()
        try:
            conn.execute(
                "INSERT INTO usuarios (nome, senha, perfil) VALUES (?, ?, ?)",
                (nome, senha_hash, perfil)
            )
            conn.commit()

            flash('Usuário cadastrado com sucesso!', 'success')
            return redirect(url_for('usuarios'))

        except sqlite3.IntegrityError:
            flash('Erro: Nome de usuário já existe.', 'danger')
            return render_template('admin/cadastro.html', nome=nome, perfil=perfil)

        finally:
            conn.close()
    return render_template('admin/cadastro.html')


# ---listar usuarios---#
@app.route('/usuarios', methods=['GET'])
@login_necessario
def usuarios():
    if not administrador():
        flash('Você não tem permissão para acessar essa página')
        return redirect(url_for('menu_principal'))

    conn = conexao()
    usuarios = conn.execute(
        'SELECT * FROM usuarios WHERE id != ?', (session['usuario_id'],)).fetchall()
    return render_template('admin/usuarios.html', usuarios=usuarios)


# ---editar perfil do usuário---#
@app.route('/editar_perfil', methods=['GET', 'POST'])
@login_necessario
def editar_perfil():
    usuario_id = session['usuario_id']
    conn = conexao()

    try:
        usuario = conn.execute(
            "SELECT * FROM usuarios WHERE id=?",
            (usuario_id,)
        ).fetchone()

        if usuario is None:
            flash('Usuário não encontrado.', 'danger')
            return redirect(url_for('menu_principal'))

        if request.method == 'POST':
            nome = request.form.get('nome', '').strip()
            senha = request.form.get('senha', '')
            confirmar_senha = request.form.get('confirmar_senha', '')

            if not nome:

                flash('Erro: O nome do usuário é obrigatório.', 'danger')

                return render_template(

                    'admin/editar_perfil.html',

                    nome=nome

                )

            if senha != confirmar_senha:

                flash('Erro: As senhas não coincidem.', 'danger')

                return render_template(

                    'admin/editar_perfil.html',

                    nome=nome

                )

            if len(senha) < 8:

                flash('Erro: A senha deve ter pelo menos 8 caracteres.', 'danger')

                return render_template(

                    'admin/editar_perfil.html',

                    nome=nome

                )

            senha_hash = bcrypt.generate_password_hash(senha).decode('utf-8')

            conn.execute(

                """

                UPDATE usuarios

                SET nome=?, senha=?

                WHERE id=?

                """,

                (nome, senha_hash, usuario_id)

            )

            conn.commit()

            # Atualiza o nome da sessão

            session['usuario'] = nome

            flash('Perfil editado com sucesso!', 'success')

            return redirect(url_for('menu_principal'))

        return render_template(

            'admin/editar_perfil.html',

            nome=usuario['nome']

        )

    except sqlite3.IntegrityError:

        flash('Erro: Nome de usuário já existe.', 'danger')

        return render_template(

            'admin/editar_perfil.html',

            nome=request.form.get('nome', '')

        )

    finally:

        conn.close()


# ---buscar usuarios---#

@app.route('/buscar_usuarios', methods=['GET'])
@login_necessario
def buscar_usuarios():

    if not administrador():

        flash('Você não tem permissão para acessar essa página')

        return redirect(url_for('menu_principal'))

    query = request.args.get('query', '').strip()

    conn = conexao()

    usuarios = conn.execute(

        'SELECT * FROM usuarios WHERE id != ?', (session['usuario_id'],)).fetchall()

    if query:

        usuarios = conn.execute(

            'SELECT * FROM usuarios WHERE nome LIKE ? AND id != ?',

            (f'%{query}%', session['usuario_id'])

        ).fetchall()

        if not usuarios:

            flash('Nenhum usuário encontrado para a busca realizada.', 'warning')

    return render_template('admin/usuarios.html', usuarios=usuarios)


# ---promover usuario---#

@app.route('/usuarios/promover/<int:id>', methods=['POST'])
@login_necessario
def promover_usuario(id):

    if not usuario_max():

        flash('Você não tem permissão para acessar essa página')

        return redirect(url_for('menu_principal'))

    conn = conexao()

    cursor = conn.execute("SELECT perfil FROM usuarios WHERE id=?", (id,))

    usuario = cursor.fetchone()

    if usuario is None:

        flash('Usuário não encontrado.', 'error')

        return redirect(url_for('usuarios'))

    elif usuario['perfil'] == 'max':

        conn.execute("UPDATE usuarios SET perfil='usuario' WHERE id=?", (id,))

        conn.commit()

    elif usuario['perfil'] == 'admin':

        conn.execute("UPDATE usuarios SET perfil='max' WHERE id=?", (id,))

        conn.commit()

        flash('Usuário promovido a Administrador Max com sucesso!', 'success')

        return redirect(url_for('usuarios'))

    elif usuario['perfil'] == 'usuario':

        conn.execute("UPDATE usuarios SET perfil='admin' WHERE id=?", (id,))

        conn.commit()

        flash('Usuário promovido a Administrador com sucesso!', 'success')

        return redirect(url_for('usuarios'))

    conn.close()

    return redirect(url_for('usuarios'))


# ---rebaixar usuario---#


@app.route('/usuarios/rebaixar/<int:id>', methods=['POST'])
@login_necessario
def rebaixar_usuario(id):

    if not usuario_max():

        flash('Você não tem permissão para acessar essa página.', 'danger')

        return redirect(url_for('menu_principal'))

    conn = conexao()

    try:

        cursor = conn.execute(

            "SELECT perfil FROM usuarios WHERE id=?",

            (id,)

        )

        usuario = cursor.fetchone()

        if usuario is None:

            flash('Usuário não encontrado.', 'error')

            return redirect(url_for('usuarios'))

        # MAX → ADMIN

        elif usuario['perfil'] == 'max':

            # Primeiro verifica se existe OUTRO MAX

            existe_outro_max = conn.execute(

                """

                SELECT COUNT(*) AS total

                FROM usuarios

                WHERE perfil='max'

                AND id != ?

                """,

                (id,)

            ).fetchone()

            # Se não existir outro MAX, bloqueia

            if existe_outro_max['total'] == 0:

                flash(

                    'Não há outro usuário com perfil "max". '

                    'Você não pode rebaixar o último usuário "max".',

                    'error'

                )

                return redirect(url_for('usuarios'))

            # Agora pode rebaixar

            conn.execute(

                "UPDATE usuarios SET perfil='admin' WHERE id=?",

                (id,)

            )

            conn.commit()

            flash(

                'Usuário rebaixado para Administrador com sucesso!',

                'success'

            )

            return redirect(url_for('usuarios'))

        # ADMIN → USUARIO

        elif usuario['perfil'] == 'admin':

            conn.execute(

                "UPDATE usuarios SET perfil='usuario' WHERE id=?",

                (id,)

            )

            conn.commit()

            flash(

                'Usuário rebaixado para Usuário com sucesso!',

                'success'

            )

            return redirect(url_for('usuarios'))

        # USUARIO → não pode rebaixar

        else:

            flash(

                'Este usuário já é um Usuário comum.',

                'warning'

            )

            return redirect(url_for('usuarios'))

    finally:

        conn.close()


# ---deletar usuario---#

@app.route('/usuarios/deletar/<int:id>', methods=['POST'])
@login_necessario
def deletar_usuario(id):

    if not usuario_max():

        flash('Você não tem permissão para acessar essa página')

        return redirect(url_for('menu_principal'))

    conn = conexao()

    cursor = conn.execute("DELETE FROM usuarios WHERE id=?", (id,))

    if cursor.rowcount == 0:

        return jsonify({'erro': 'Usuário não encontrado'}), 404

    conn.commit()

    return redirect(url_for('usuarios'))


# ---logout do usuario---#

@app.route('/logout')
@login_necessario
def logout():

    if not usuario_logado():

        flash('VÁ LOGAR', 'error')

        return redirect(url_for('login'))

    session.clear()

    return redirect(url_for('login'))


# ---menu principal---#


@app.route('/menu_principal')
@login_necessario
def menu_principal():

    if not usuario_logado():

        flash('VÁ LOGAR', 'error')

        return redirect(url_for('login'))

    return render_template('admin/card.html')


@app.route('/')
def index():

    return render_template('admin/login.html')


if __name__ == '__main__':

    init_db()

    app.run(debug=True, host='0.0.0.0', port=4000)
