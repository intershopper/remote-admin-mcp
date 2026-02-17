import os
from dotenv import load_dotenv
from .models import ServerConfig


def load_servers() -> dict[str, ServerConfig]:
    """Load server configurations from environment variables."""
    load_dotenv()
    
    servers = {}
    i = 1
    
    while True:
        name = os.getenv(f"SSH_SERVER_{i}_NAME")
        if not name:
            break
            
        host = os.getenv(f"SSH_SERVER_{i}_HOST")
        port = int(os.getenv(f"SSH_SERVER_{i}_PORT", "22"))
        user = os.getenv(f"SSH_SERVER_{i}_USER")
        password = os.getenv(f"SSH_SERVER_{i}_PASSWORD")
        
        if not all([host, user, password]):
            raise ValueError(f"Incomplete configuration for server {i}")
        
        servers[name] = ServerConfig(
            name=name,
            host=host,
            port=port,
            user=user,
            password=password
        )
        i += 1
    
    return servers
