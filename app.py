from flask import Flask, jsonify, request, render_template, url_for, redirect, session, flash
import sqlite3
from flask_bcrypt import Bcrypt
from datetime import datetime
from functools import wraps


app = Flask(__name__)
DATABASE = 'database.db'
app.secret_key = 'your_secret_key'
bcrypt = Bcrypt(app)


def init_db():
    with sqlite3.connect(DATABASE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS livros(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                titulo TEXT NOT NULL,
                autor TEXT NOT NULL,
                genero TEXT NOT NULL,
                lancado INTEGER NOT NULL
            )
        '''),

        conn.execute('''
            CREATE TABLE IF NOT EXISTS usuarios(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL UNIQUE,
                senha TEXT NOT NULL,
                perfil TEXT NOT NULL DEFAULT 'usuario'
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
            senha_usermax = bcrypt.generate_password_hash('max123').decode('utf-8')
            cursor.execute('INSERT INTO usuarios (nome, senha, perfil) VALUES (?, ?, ?)', ('usermax', senha_usermax, 'max'))
        
        conn.commit()

        print("\n ---- BIBLIOTECA ABERTA ---- ")

#---conexao com o banco de dados---#
def conexao():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

#---verifica se o usuario está logado---#
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

#---livros---#
@app.route('/livros', methods=['GET'])
@login_necessario
def livros():

    if not usuario_logado():
        flash('VÁ LOGAR', 'error')
        return redirect(url_for('login'))

    conn = conexao()
    livros = conn.execute('SELECT * FROM livros')
    return render_template('admin/livros.html', livros=livros)

#---buscar livros---#
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

#---emprestimos---#
@app.route('/empretimos', methods=['GET'])
@login_necessario
def emprestimos():

    
    return render_template('admin/empretimos.html', livros=livros)

#---adicionar livro---#
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

        conn = conexao()
        conn.execute(
                'INSERT INTO livros (titulo, genero, autor, lancado) VALUES (?, ?, ?, ?)', (titulo, genero, autor, lancado))
        conn.commit()

        return redirect(url_for('livros'))
    return render_template('admin/add_livro.html')

#---editar livro---#
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

        conn = conexao()
        cursor = conn.execute(
                "UPDATE livros SET titulo=?, autor=?, genero=?, lancado=? WHERE id=?", (
                    titulo, autor, genero, lancado, id)
            )
        conn.commit()
        return redirect(url_for('livros'))
    

    conn = conexao()
    livro = conn.execute("SELECT * FROM livros WHERE id = ?", (id,)).fetchone()
    conn.close()
    if livro is None:
        return "Livro não encontrado", 404

    return render_template('admin/edit.html', livro=livro)

#---login do usuario---#
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


#---cadastro de usuarios---#
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

#---listar usuarios---#
@app.route('/usuarios', methods=['GET'])
@login_necessario
def usuarios():

    if not administrador():
        flash('Você não tem permissão para acessar essa página')
        return redirect(url_for('menu_principal'))

    conn = conexao()
    usuarios = conn.execute('SELECT * FROM usuarios')
    return render_template('admin/usuarios.html', usuarios=usuarios)

#---buscar usuarios---#        
@app.route('/buscar_usuarios', methods=['GET'])
@login_necessario
def buscar_usuarios():

    if not administrador():
        flash('Você não tem permissão para acessar essa página')
        return redirect(url_for('menu_principal'))


    query = request.args.get('query', '').strip()

    conn = conexao()
    usuarios = conn.execute('SELECT * FROM usuarios')

    if query:
        usuarios = conn.execute(
            'SELECT * FROM usuarios WHERE nome LIKE ?', 
            (f'%{query}%',)
        ).fetchall()

        if not usuarios:
            flash('Nenhum usuário encontrado para a busca realizada.', 'warning')
    return render_template('admin/usuarios.html', usuarios=usuarios)


#---promover usuario---#
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

#---rebaixar usuario---#
@app.route('/usuarios/rebaixar/<int:id>', methods=['POST'])
@login_necessario
def rebaixar_usuario(id):

    if not usuario_max():
        flash('Você não tem permissão para acessar essa página')
        return redirect(url_for('menu_principal'))

    conn = conexao()
    cursor = conn.execute("SELECT perfil FROM usuarios WHERE id=?", (id,))
    usuario = cursor.fetchone()
    
    if usuario is None:
        conn.close()
        flash('Usuário não encontrado.', 'error')
        return redirect(url_for('usuarios'))
    
    elif usuario['perfil'] == 'max':
        conn.execute("UPDATE usuarios SET perfil='usuario' WHERE id=?", (id,))
        conn.commit()

        flash('Usuário rebaixado para Usuário comum com sucesso!', 'success')
        return redirect(url_for('usuarios'))
    else:
        conn.close()
        flash('Este usuário não é um administrador.', 'error')
        return redirect(url_for('usuarios'))
    
#---deletar usuario---#
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

#---deletar livro---#
@app.route('/livros/deletar/<int:id>', methods=['POST'])
@login_necessario
def deletar_livro(id):

    if not administrador():
        flash('Você não tem permissão para acessar essa página')
        return redirect(url_for('menu_principal'))

    conn = conexao()
    cursor = conn.execute("DELETE FROM livros WHERE id=?", (id,))

    if cursor.rowcount == 0:
        return jsonify({'erro': 'Livro não encontrado'}), 404
    conn.commit()
    return redirect(url_for('livros'))

#---logout do usuario---#
@app.route('/logout')
@login_necessario
def logout():
    session.clear()
    return redirect(url_for('login'))

#---menu principal---#
@app.route('/menu_principal')
@login_necessario
def menu_principal():

    return render_template('admin/card.html')


@app.route('/')
def index():
    return render_template('admin/login.html')

if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=4000)
