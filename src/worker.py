import gobject

from threading import Thread, Lock, Condition

# Run this once during application start:
gobject.threads_init()

# Use this thread to postpone work and update the GUI asynchronously.
# The idea is to push a function and some parameters, and that function
# will be executed in a separate thread. This function must NOT update
# the UI directly, it must return another function with its own arguments
# to be queued in the main thread's event loop with gobject.idle_add. 
# (See http://faq.pygtk.org/index.py?file=faq20.006.htp&req=show)
class Worker(Thread):
    def __init__(self):
        Thread.__init__(self)
        self.lock = Lock()
        self.cond = Condition(self.lock)
        self.stopped = False
        self.queue = []

    def run(self):
        while True:
            job = None
            with self.cond:
                if self.stopped:
                    return
                if not self.queue:
                    self.cond.wait()
                else:
                    job, params = self.queue.pop(0)
            if not job:
                continue
            self.execute(job, params)

    def execute(self, job, params):
        try:
            func, args = job(*params)
            gobject.idle_add(func, *args)
        except Exception, e:
            print "Warning:", e

    def stop(self):
        with self.cond:
            self.stopped = True
            self.cond.notify_all()

    def clear(self):
        with self.cond:
            self.queue = []
            self.cond.notify_all()

    def push(self, job):
        with self.cond:
            self.queue.append(job)
            self.cond.notify_all()

