"""Supabase配置"""

from typing import Optional
from pydantic import BaseModel


class SupabaseConfig(BaseModel):
    """Supabase数据库配置"""
    
    url: str
    key: str
    service_role_key: Optional[str] = None
    
    # PostgreSQL连接参数
    host: str
    port: int = 5432
    database: str
    user: str
    password: str
    
    # 向量存储配置
    table_name: str = "documents"
    collection_name: str = "default"
    
    @classmethod
    def from_env(cls, env_dict: dict) -> "SupabaseConfig":
        """从环境变量创建配置"""
        return cls(
            url=env_dict.get("SUPABASE_URL"),
            key=env_dict.get("SUPABASE_KEY"),
            service_role_key=env_dict.get("SUPABASE_SERVICE_KEY"),
            host=env_dict.get("SUPABASE_DB_HOST"),
            port=int(env_dict.get("SUPABASE_DB_PORT", "5432")),
            database=env_dict.get("SUPABASE_DB_NAME"),
            user=env_dict.get("SUPABASE_DB_USER"),
            password=env_dict.get("SUPABASE_DB_PASSWORD"),
            table_name=env_dict.get("SUPABASE_TABLE_NAME", "documents"),
            collection_name=env_dict.get("SUPABASE_COLLECTION_NAME", "default")
        )
    
    @property
    def postgres_url(self) -> str:
        """获取PostgreSQL连接URL"""
        from urllib.parse import quote_plus
        
        # URL编码用户名和密码以处理特殊字符
        encoded_user = quote_plus(self.user)
        encoded_password = quote_plus(self.password)
        
        # 对于SQLAlchemy使用postgresql+psycopg，对于直连使用postgresql
        return f"postgresql+psycopg://{encoded_user}:{encoded_password}@{self.host}:{self.port}/{self.database}"
    
    @property
    def direct_postgres_url(self) -> str:
        """获取直连PostgreSQL URL（用于psycopg直连）"""
        from urllib.parse import quote_plus
        
        encoded_user = quote_plus(self.user)
        encoded_password = quote_plus(self.password)
        
        return f"postgresql://{encoded_user}:{encoded_password}@{self.host}:{self.port}/{self.database}"
