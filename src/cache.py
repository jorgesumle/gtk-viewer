# Cache implementation

class Cache:
    def __init__(self, limit=None, shared=False):
        self.keys = []
        self.limit = limit
        self.shared = shared
        self.store = {}
        self.hits = 0
        self.misses = 0

    def __add_key(self, key):
        if self.limit is None:
            return

        if len(self.keys) == self.limit:
            older = self.keys[0]
            del self.store[older]
            del self.keys[0]

        self.keys.append(key)

    def __refresh_key(self, key):
        if self.limit is None:
            return

        del self.keys[self.keys.index(key)]
        self.keys.append(key)

    def __setitem__(self, key, value):
        self.__add_key(key)
        self.store[key] = value

    def __getitem__(self, key):
        try:
            value = self.store[key]
            self.hits += 1
            self.__refresh_key(key)
            return value
        except:
            self.misses += 1
            raise

def cached(cache_=None):
    def func(method):
        def wrapper(self, *args, **kwargs):
            if not cache_:
                if not hasattr(self, "__cache__"):
                    self.__cache__ = Cache()
                cache = self.__cache__
            else:
                cache = cache_
    
            # if the cache is shared, self must NOT be
            # included in the key (so multiple instances
            # calling the same method with the same args
            # share the same result).
            if cache.shared:
                key = (method.__name__,
                       args,
                       tuple(kwargs.items()))
            else:
                key = (hash(self),
                       method.__name__,
                       args,
                       tuple(kwargs.items()))

            try:
                return cache[key]
            except:
                value = method(self, *args, **kwargs)
                cache[key] = value
                return value
        return wrapper
    return func

