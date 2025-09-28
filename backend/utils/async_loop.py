import asyncio
import threading



# Создаем отдельный event loop для Flask
_flask_loop = None
_flask_loop_lock = threading.Lock()



def get_flask_loop():
    global _flask_loop
    if _flask_loop is None:
        with _flask_loop_lock:
            if _flask_loop is None:
                _flask_loop = asyncio.new_event_loop()
                # Запускаем loop в отдельном потоке
                def run_loop(loop):
                    asyncio.set_event_loop(loop)
                    loop.run_forever()
                
                thread = threading.Thread(target=run_loop, args=(_flask_loop,), daemon=True)
                thread.start()
    return _flask_loop

def run_async(coro):
    """Запускает асинхронную функцию в Flask loop"""
    loop = get_flask_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result()