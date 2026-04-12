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
        password = os.getenv(f"SSH_SERVER_{i}_PASSWORD", "")
        key_file = os.getenv(f"SSH_SERVER_{i}_KEY_FILE", "")
        if key_file:
            key_file = os.path.expanduser(key_file)
        
        if not all([host, user]) or not any([password, key_file]):
            raise ValueError(f"Incomplete configuration for server {i} (need password or key_file)")
        
        servers[name] = ServerConfig(
            name=name, host=host, port=port, user=user,
            password=password, key_file=key_file,
        )
        i += 1
    
    return servers
