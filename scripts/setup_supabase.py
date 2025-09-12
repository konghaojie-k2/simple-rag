#!/usr/bin/env python3
"""
Supabase设置脚本
安装依赖并配置Supabase数据库
"""

import os
import sys
import subprocess
from pathlib import Path


def run_command(cmd, check=True):
    """运行命令"""
    print(f"执行命令: {cmd}")
    result = subprocess.run(cmd, shell=True, check=check)
    return result.returncode == 0


def install_dependencies():
    """安装Python依赖"""
    print("正在安装Python依赖...")
    
    # 检查uv是否已安装
    if not run_command("uv --version", check=False):
        print("错误: uv未安装，请先安装uv包管理器")
        print("安装命令: curl -LsSf https://astral.sh/uv/install.sh | sh")
        sys.exit(1)
    
    # 同步依赖
    if not run_command("uv sync"):
        print("错误: 依赖安装失败")
        sys.exit(1)
    
    print("依赖安装完成")


def check_env_file():
    """检查环境变量文件"""
    env_file = Path(".env")
    env_example = Path("env.example")
    
    if not env_file.exists():
        if env_example.exists():
            print("正在创建.env文件...")
            env_file.write_text(env_example.read_text())
            print("已创建.env文件，请根据实际情况修改配置")
        else:
            print("错误: 找不到env.example文件")
            sys.exit(1)
    else:
        print(".env文件已存在")
    
    return env_file


def load_env_vars(env_file):
    """加载环境变量"""
    env_vars = {}
    
    try:
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    env_vars[key] = value
    except Exception as e:
        print(f"错误: 读取环境变量文件失败: {e}")
        sys.exit(1)
    
    return env_vars


def check_supabase_config(env_vars):
    """检查Supabase配置"""
    required_vars = [
        'SUPABASE_URL',
        'SUPABASE_KEY', 
        'SUPABASE_DB_HOST',
        'SUPABASE_DB_PASSWORD'
    ]
    
    missing_vars = []
    for var in required_vars:
        if not env_vars.get(var) or env_vars[var].startswith('your-'):
            missing_vars.append(var)
    
    if missing_vars:
        print("错误: 以下Supabase配置变量需要设置:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\n请在.env文件中设置这些变量后重新运行脚本")
        sys.exit(1)
    
    print("Supabase配置检查通过")


def init_supabase_database(env_vars):
    """初始化Supabase数据库"""
    print("正在初始化Supabase数据库...")
    
    # 读取SQL初始化脚本
    sql_file = Path("scripts/init_supabase.sql")
    if not sql_file.exists():
        print("错误: 找不到init_supabase.sql文件")
        sys.exit(1)
    
    # 尝试多种方法执行SQL
    success = False
    
    # 方法1: 尝试使用psycopg直接连接
    try:
        import psycopg
        success = init_with_psycopg(env_vars, sql_file)
        if success:
            print("✅ 数据库初始化完成（使用psycopg）")
            return
    except ImportError:
        print("psycopg未安装，尝试其他方法...")
    except Exception as e:
        print(f"psycopg连接失败: {e}")
    
    # 方法2: 尝试使用Supabase Python客户端
    try:
        success = init_with_supabase_client(env_vars, sql_file)
        if success:
            print("✅ 数据库初始化完成（使用Supabase客户端）")
            return
    except Exception as e:
        print(f"Supabase客户端初始化失败: {e}")
    
    # 方法3: 检查是否有psql命令
    if run_command("psql --version", check=False):
        db_url = f"postgresql://{env_vars.get('SUPABASE_DB_USER', 'postgres')}:{env_vars['SUPABASE_DB_PASSWORD']}@{env_vars['SUPABASE_DB_HOST']}:{env_vars.get('SUPABASE_DB_PORT', '5432')}/{env_vars.get('SUPABASE_DB_NAME', 'postgres')}"
        cmd = f'psql "{db_url}" -f "{sql_file}"'
        if run_command(cmd, check=False):
            print("✅ 数据库初始化完成（使用psql）")
            return
    
    # 所有方法都失败，提供手动操作指南
    print("⚠️ 自动数据库初始化失败")
    print_manual_setup_guide(sql_file)


def init_with_psycopg(env_vars, sql_file):
    """使用psycopg直接执行SQL"""
    import psycopg
    
    connection_params = {
        "host": env_vars['SUPABASE_DB_HOST'],
        "port": int(env_vars.get('SUPABASE_DB_PORT', '5432')),
        "dbname": env_vars.get('SUPABASE_DB_NAME', 'postgres'),
        "user": env_vars.get('SUPABASE_DB_USER', 'postgres'),
        "password": env_vars['SUPABASE_DB_PASSWORD'],
        "sslmode": "require"
    }
    
    with psycopg.connect(**connection_params) as conn:
        with conn.cursor() as cur:
            sql_content = sql_file.read_text(encoding='utf-8')
            cur.execute(sql_content)
            conn.commit()
    
    return True


def init_with_supabase_client(env_vars, sql_file):
    """使用Supabase客户端执行SQL"""
    from supabase import create_client
    
    supabase = create_client(
        env_vars['SUPABASE_URL'],
        env_vars.get('SUPABASE_SERVICE_KEY', env_vars['SUPABASE_KEY'])
    )
    
    sql_content = sql_file.read_text(encoding='utf-8')
    
    # 分割SQL语句（简单分割，可能需要改进）
    statements = [stmt.strip() for stmt in sql_content.split(';') if stmt.strip()]
    
    for statement in statements:
        if statement and not statement.startswith('--'):
            try:
                supabase.rpc('exec_sql', {'sql': statement})
            except Exception as e:
                # 某些语句可能失败（如表已存在），继续执行
                print(f"执行语句时警告: {str(e)[:100]}...")
    
    return True


def print_manual_setup_guide(sql_file):
    """打印手动设置指南"""
    print("\n" + "="*60)
    print("手动数据库初始化指南")
    print("="*60)
    print("请按以下步骤手动初始化数据库：")
    print()
    print("1. 打开Supabase控制台: https://supabase.com/dashboard")
    print("2. 选择您的项目")
    print("3. 点击左侧菜单 'SQL Editor'")
    print("4. 点击 'New query'")
    print("5. 复制以下文件的内容到查询编辑器:")
    print(f"   {sql_file.absolute()}")
    print("6. 点击 'Run' 执行SQL")
    print()
    print("或者，您可以:")
    print("1. 安装PostgreSQL客户端工具:")
    print("   - Windows: https://www.postgresql.org/download/windows/")
    print("   - 或安装psycopg: pip install psycopg[binary]")
    print("2. 重新运行此脚本")
    print("="*60)


def create_directories():
    """创建必要的目录"""
    directories = ['logs', 'api_server']
    
    for dir_name in directories:
        dir_path = Path(dir_name)
        dir_path.mkdir(exist_ok=True)
        print(f"创建目录: {dir_path}")


def print_next_steps():
    """打印后续步骤"""
    print("\n" + "="*50)
    print("设置完成！后续步骤:")
    print("="*50)
    print("1. 确认.env文件中的Supabase配置正确")
    print("2. 如果数据库初始化失败，请手动在Supabase中执行scripts/init_supabase.sql")
    print("3. 启动API服务器:")
    print("   cd api_server")
    print("   uv run python main.py")
    print("4. API文档地址: http://localhost:8002/docs")
    print("5. 测试健康检查: curl http://localhost:8002/health")
    print("="*50)


def main():
    """主函数"""
    print("开始设置Supabase RAG系统...")
    
    # 检查Python版本
    if sys.version_info < (3, 11):
        print("错误: 需要Python 3.11或更高版本")
        sys.exit(1)
    
    # 切换到项目根目录
    os.chdir(Path(__file__).parent.parent)
    
    # 安装依赖
    install_dependencies()
    
    # 检查环境变量文件
    env_file = check_env_file()
    
    # 加载环境变量
    env_vars = load_env_vars(env_file)
    
    # 检查Supabase配置
    check_supabase_config(env_vars)
    
    # 创建必要目录
    create_directories()
    
    # 初始化数据库
    init_supabase_database(env_vars)
    
    # 打印后续步骤
    print_next_steps()


if __name__ == "__main__":
    main()
