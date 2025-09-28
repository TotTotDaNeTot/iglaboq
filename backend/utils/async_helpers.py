import asyncio



def run_async(coro):
    """Синхронная обертка для асинхронных функций"""
    try:
        # Пытаемся использовать существующий loop
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # Если loop уже запущен, создаем новый
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
    except RuntimeError:
        # Если нет текущего loop, создаем новый
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    try:
        return loop.run_until_complete(coro)
    finally:
        if not loop.is_running():
            loop.close()