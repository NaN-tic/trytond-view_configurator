from trytond.pool import PoolMeta


class View(metaclass=PoolMeta):
    __name__ = 'ir.ui.view'

    def get_rec_name(self, name):
        return super().get_rec_name(name) + " (%s)" % self.name
