from flask import Flask, jsonify, request, render_template, url_for, redirect, session, flash
import sqlite3
from flask_bcrypt import Bcrypt
from datetime import datetime


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
            
        ''')
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
            senha_admin = bcrypt.generate_password_hash('admin123').decode('utf-8')
            cursor.execute('INSERT INTO usuarios (nome, senha, perfil) VALUES (?, ?, ?)', ('admin', senha_admin, 'admin'))
        
        conn.commit()

        print("\n ---- BIBLIOTECA ABERTA ---- ")

def conexao():
    with sqlite3.connect(DATABASE) as conn:
        conn.row_factory = sqlite3.Row
        return conn

@app.route('/livros', methods=['GET'])
def livros():
    conn = conexao()
    livros = conn.execute('SELECT * FROM livros')
    return render_template('admin/livros.html', livros=livros)

@app.route('/buscar_livros', methods=['GET'])
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


@app.route('/book_lending', methods=['GET'])
def book_lending():
    conn = conexao()
    livros = conn.execute('SELECT * FROM livros')
    return render_template('admin/book_lending.html', livros=livros)


@app.route('/add_livro', methods=['GET', 'POST'])
def add_livro():
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


@app.route('/edit/<int:id>', methods=['POST', 'GET'])
def edit(id):

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



@app.route("/login", methods=['GET', 'POST'])
def login():
    if 'usuario' in session:
        return redirect(url_for('menu_principal'))

    if request.method == 'POST':

        nome = request.form.get('nome', '').strip()
        senha = request.form.get('senha', '')

        if not nome or not senha:
            return render_template('login.html', erro='Preencha todos os campos.')

        conn = conexao()
        usuario = conn.execute(
                "SELECT * FROM usuarios WHERE nome=?", (nome,)).fetchone()

        if usuario:
            senha_correta = bcrypt.check_password_hash(usuario['senha'], senha)
            if senha_correta:
                session['usuario'] = usuario['nome']
                session['usuario_id'] = usuario['id']
                session['perfil'] = usuario['perfil']
                return redirect(url_for('menu_principal'))

        return render_template('admin/login.html', erro='Usuário ou senha incorretos.')

    return render_template('admin/login.html')


def administrador():
    return session.get('perfil') == 'admin'


@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        senha = request.form.get('senha', '')
        confirmar_senha = request.form.get('confirmar_senha', '')
        perfil = request.form.get('perfil', 'usuario')

        perfil = request.form.get('perfil', 'usuario')  # Padrão para 'usuario' se não fornecido

        # 1. Validações
        if not nome:
            flash('Erro: O nome de usuário é obrigatório.', 'danger')
            return render_template('admin/cadastro.html', nome=nome, perfil=perfil)

        if senha != confirmar_senha:
            flash('Erro: As senhas não coincidem.', 'danger')
            return render_template('admin/cadastro.html', nome=nome, perfil=perfil)

        if len(senha) < 8:
            flash('Erro: A senha deve ter pelo menos 8 caracteres.', 'danger')
            return render_template('admin/cadastro.html', nome=nome, perfil=perfil)

        # 2. Criptografia
        senha_hash = bcrypt.generate_password_hash(senha).decode('utf-8')

        # 3. Persistência no Banco de Dados
        conn = conexao()
        try:
            conn.execute(
                "INSERT INTO usuarios (nome, senha, perfil) VALUES (?, ?, ?)", 
                (nome, senha_hash, perfil)
            )
            conn.commit()
            
            # Flash movido para DENTRO do sucesso
            flash('Usuário cadastrado com sucesso!', 'success')
            return redirect(url_for('usuarios')) # Redireciona para o login ou lista de usuários

        except sqlite3.IntegrityError:
            flash('Erro: Nome de usuário já existe.', 'danger')
            return render_template('admin/cadastro.html', nome=nome, perfil=perfil)
            
        finally:
            conn.close() # Garante que a conexão sempre será fechada

    # Carregamento da página via GET
    return render_template('admin/cadastro.html')
        


@app.route('/livros/deletar/<int:id>', methods=['POST'])
def deletar_livro(id):
        conn = conexao()
        cursor = conn.execute("DELETE FROM livros WHERE id=?", (id,))
        if cursor.rowcount == 0:
            return jsonify({'erro': 'Livro não encontrado'}), 404
        conn.commit()
        return redirect(url_for('livros'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/menu_principal')
def menu_principal():
    return render_template('admin/card.html')

@app.route('/')
def index():
    return render_template('admin/login.html')


if __name__ == '__main__':
    init_db()
    app.run(debug=True, host='0.0.0.0', port=4000)
