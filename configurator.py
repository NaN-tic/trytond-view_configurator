# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
import datetime
from collections import defaultdict
from trytond.model import (Workflow, ModelSQL, ModelView, fields,
    sequence_ordered, UnionMixin)
from trytond.pool import PoolMeta, Pool
from trytond.pyson import Eval, If, Bool
from sql import Column, Literal
from lxml import etree
from trytond.rpc import RPC
from trytond.transaction import Transaction

__all__ = ['ViewConfigurator', 'ViewConfiguratorLine', 'ModelViewMixin'
    'ViewConfiguratorSnapshot', 'ViewConfiguratorLineField',
    'ViewConfiguratorLineButton']


class ModelViewMixin:

    @classmethod
    def fields_view_get(cls, view_id=None, view_type='form'):
        print("A:", view_id, view_type, cls.__name__)
        result = super(ModelViewMixin, cls).fields_view_get(view_id, view_type)

        if cls.__name__  == 'view.configurator':
            return result

        if result.get('type') != 'tree':
            return result

        view_id = view_id or None
        ViewConfigurator = Pool().get('view.configurator')
        viewConfigurator = ViewConfigurator.search([
            ('state', '=', 'confirmed'),
            ('model.model','=', cls.__name__), ('view','=', view_id)],
            limit=1)

        if not viewConfigurator:
            return result

        viewConfigurator, = viewConfigurator
        result['arch'] = viewConfigurator.view_xml

        #TODO: cache
        return result

class ViewConfiguratorSnapshot(ModelSQL, ModelView):
    'View configurator Snapshot'
    __name__ = 'view.configurator.snapshot'

    view = fields.Many2One('view.configurator', 'View', required=True)
    field = fields.Many2One('ir.model.field', 'Field')
    button = fields.Many2One('ir.model.button', 'Button')


class ViewConfigurator(Workflow, ModelSQL, ModelView):
    '''View Configurator'''
    __name__ = 'view.configurator'

    model= fields.Many2One('ir.model', 'Model', required=True, select=True)
    model_str = fields.Function(fields.Char('Model String'), 'get_model_str')
    user = fields.Many2One('res.user', 'User')
    view = fields.Many2One('ir.ui.view', 'View', domain=[('type', '=', 'tree')],
        select=True)
    snapshot = fields.One2Many('view.configurator.snapshot', 'view', 'Snapshot',
        readonly=True)
    field_lines = fields.One2Many('view.configurator.line.field', 'view',
    'Lines')
    button_lines = fields.One2Many('view.configurator.line.button', 'view',
        'Lines')
    lines = fields.One2Many('view.configurator.line', 'view',
        'Lines')
    view_xml = fields.Text('View xml')
    state = fields.Selection([('draft','Draft'), ('confirmed', 'Confirmed'),
        ('cancel', 'Cancel')], 'State', readonly=True, select=True,
        required=True)


    @classmethod
    def __setup__(cls):
        super(ViewConfigurator, cls).__setup__()
        cls._transitions |= set((
                ('draft', 'confirmed'),
                ('confirmed', 'draft'),
                ('confirmed', 'cancel'),
                ('draft', 'cancel')))
        cls._buttons.update({
            'confirmed': {
                'invisible': (Eval('state') != 'draft'),
                'icon': 'tryton-go-next',
                },
            'draft': {
                'invisible': (Eval('state') == 'draft'),
                },
            'cancel':{
                'invisible':(Eval('state') != 'cancel'),
                },
            'get_snapshot': {},
            })

        cls.__rpc__.update({
            'get_custom_view': RPC(readonly=False, instantiate=1),
        })

    @staticmethod
    def default_state():
        return 'draft'

    @classmethod
    @ModelView.button
    @Workflow.transition('draft')
    def draft(cls, views):
        pass

    @classmethod
    @ModelView.button
    @Workflow.transition('confirmed')
    def confirmed(cls, views):
        for view in views:
            view.generate_xml()

    @classmethod
    @ModelView.button
    @Workflow.transition('cancel')
    def cancel(cls, views):
        pass

    @classmethod
    def get_custom_view(cls, model_name, view_ids):
        pool = Pool()
        print("Model:", model_name, "view_ids:", view_ids)
        Model = pool.get('ir.model')
        View = pool.get('ir.ui.view')
        User = pool.get('res.user')
        user = Transaction().user
        domain = [('model.model','=', model_name)]
        if view_ids:
            domain += [('view', 'in', view_ids)]

        custom_views = cls.search(domain, limit=1)
        if custom_views:
            custom_view, = custom_views
            cls.draft([custom_view])
            custom_view.create_snapshot()
            cls.confirmed([custom_view])
            print("res:", custom_view.id)
            return custom_view.id

        model, = Model.search([('model', '=', model_name)])

        views = None
        if view_ids:
            views = View.search([('id', 'in',[x.id for x in view_ids]), ('type','=', 'tree')],
                limit=1)


        custom_view = cls()
        custom_view.model = model
        if views:
            custom_view.view = View(views[0])
        custom_view.user = user
        custom_view.save()
        custom_view.create_snapshot()
        cls.confirmed([custom_view])
        print("return:", custom_view)
        return custom_view.id

    def get_model_str(self, name=None):
        print("*"*100, self.model and self.model.model or '')
        return self.model and self.model.model or ''

    def generate_xml(self):
        xml = '<?xml version="1.0"?>'
        xml += '<tree>'
        for line in self.lines:
            if line.field:
                xml+= "<field name='%s' expand='%s' tree_invisible='%s'/>" % (
                    line.field.name, line.expand or 0, 1 if line.searchable else 0)
            if line.button:
                xml += "<button name='%s' tree_invisible='%s' string='%s'/>" % (
                    line.button.name, line.expand or 0, line.button.string
                )
        xml += '</tree>'
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.fromstring(xml, parser)
        xarch, xfields = self._view_look_dom_arch(tree, 'tree')
        self.view_xml = xarch
        self.save()


    def create_snapshot(self):
        pool = Pool()
        Model = pool.get(self.model.model)
        Snapshot = pool.get('view.configurator.snapshot')
        FieldLine = pool.get('view.configurator.line.field')
        ButtonLine = pool.get('view.configurator.line.button')
        Button = pool.get('ir.model.button')

        result = Model.fields_view_get(self.view, view_type='tree')
        parser = etree.XMLParser(remove_comments=True)
        tree = etree.fromstring(result['arch'], parser=parser)

        resources = {}
        existing_snapshot = []
        for field in self.model.fields:
            resources[field.name] = field
        for line in self.snapshot:
            if line.field:
                existing_snapshot.append(line.field)
            elif line.button:
                existing_snapshot.append(line.button)

        sbuttons = Button.search([('model', '=', self.model)])
        buttons = {}
        for button in sbuttons:
            resources[button.name] = button

        def create_lines(type_, resource):
            if type_ == 'field':
                line = FieldLine()
                line.type = 'ir.model.field'
                line.field = resource
            elif type_ == 'button':
                line = ButtonLine()
                line.type = 'ir.model.button'
                line.button = resource
            line.searchable = False
            line.expand=0
            line.sequence=100
            line.view = self
            line.save()

        def create_snapshot(type_, resource):
            snapshot = Snapshot()
            snapshot.view = self
            if type_ == 'field':
                snapshot.field = resource
            else:
                snapshot.button = resource
            snapshot.save()
            existing_snapshot.append(resource)

        for child in tree:
            type_ = child.tag
            view_xml = etree.tostring(child, encoding='utf-8').decode('utf-8')
            attributes = child.attrib
            name = attributes['name']
            if resources[name] not in existing_snapshot:
                create_lines(type_, resources[name])
                create_snapshot(type_, resources[name])


    @classmethod
    @ModelView.button
    def get_snapshot(cls, views):
        for view in views:
            view.create_snapshot()


class ViewConfiguratorLineButton(sequence_ordered(), ModelSQL, ModelView):
    '''View Configurator Line Button'''
    __name__ = 'view.configurator.line.button'

    view = fields.Many2One('view.configurator',
        'View Configurator', required=True)
    button = fields.Many2One('ir.model.button', 'Button')
    expand = fields.Integer('Expand')
    searchable = fields.Boolean('Searchable')
    type = fields.Selection([('ir.model.button', 'Button')], 'Type')
    parent_model = fields.Function(fields.Many2One('ir.model', 'Model'),
        'on_change_with_parent_model')

    @staticmethod
    def default_type():
        return 'ir.model.button'

    @staticmethod
    def default_type():
        return 'ir.model.field'

    @fields.depends('view', '_parent_view.model')
    def on_change_with_parent_model(self, name=None):
        if self.view:
            return self.view.model
        return None

class ViewConfiguratorLineField(sequence_ordered(),ModelSQL, ModelView):
    '''View Configurator Line Field'''
    __name__ = 'view.configurator.line.field'

    view = fields.Many2One('view.configurator',
        'View Configurator', required=True)
    field = fields.Many2One('ir.model.field', 'Field')
    expand = fields.Integer('Expand')
    searchable = fields.Boolean('Searchable')
    type = fields.Selection([('ir.model.field', 'Field')], 'Type')
    parent_model = fields.Function(fields.Many2One('ir.model', 'Model'),
        'on_change_with_parent_model')

    @staticmethod
    def default_type():
        return 'ir.model.field'

    @fields.depends('view', '_parent_view.model')
    def on_change_with_parent_model(self, name=None):
        if self.view:
            return self.view.model
        return None

class ViewConfiguratorLine(UnionMixin, sequence_ordered(), ModelSQL, ModelView):
    '''View Configurator Line'''
    __name__ = 'view.configurator.line'

    view = fields.Many2One('view.configurator',
        'View Configurator', required=True)
    type = fields.Selection([('ir.model.button', 'Button'),
        ('ir.model.field', 'Field')], 'Type')
    field = fields.Many2One('ir.model.field', 'Field',
        domain=[('model', '=', Eval('parent_view.model'))],
        depends=['parent_model'])
    button = fields.Many2One('ir.model.button', 'Button')
    expand = fields.Integer('Expand')
    searchable = fields.Boolean('Searchable')
    parent_model = fields.Function(fields.Many2One('ir.model', 'Model'),
        'on_change_with_parent_model')

    @staticmethod
    def default_expand():
        return 0

    @staticmethod
    def default_searchable():
        return False

    @fields.depends('view', '_parent_view.model')
    def on_change_with_parent_model(self, name=None):
        if self.view:
            return self.view.model.id
        return None

    def get_parent_model(self, name):
        return self.view.model.id

    @staticmethod
    def union_models():
        return ['view.configurator.line.field',
            'view.configurator.line.button']

    @classmethod
    def union_column(cls, name, field, table, Model):
        value = Literal(None)
        if name == 'button':
            if 'button' in Model.__name__:
                value = Column(table, 'button')
            return value
        if name == 'field':
            if 'field' in Model.__name__:
                value = Column(table, 'field')
            return value
        return super(ViewConfiguratorLine, cls).union_column(name,
            field, table, Model)

    @classmethod
    def create(cls, vlist):
        pool = Pool()
        models_to_create = defaultdict(list)
        for l in vlist:
            print("1:", l)
            type_ = l['type']
            type_ = 'view.configurator.line.field'
            if 'button' in l['type'] :
                type_ = 'view.configurator.line.button'
                if 'field' in l:
                    del l['field']
            else:
                if 'button' in l:
                    del l['button']
            models_to_create[type_].append(l)

        for model, arguments in models_to_create.items():
            Model = pool.get(model)
            print("3:", Model, model, arguments)
            Model.create(arguments)



    @classmethod
    def write(cls, *args):
        pool = Pool()
        models_to_write = defaultdict(list)
        actions = iter(args)
        for models, values in zip(actions, actions):
            for model in models:
                record = cls.union_unshard(model.id)
                models_to_write[record.__name__].extend(([record], values))
        for model, arguments in models_to_write.items():
            Model = pool.get(model)
            Model.write(*arguments)

    @classmethod
    def delete(cls, lines):
        pool = Pool()
        models_to_delete = defaultdict(list)
        for model in lines:
            record = cls.union_unshard(model.id)
            models_to_delete[record.__name__].append(record)
        for model, records in models_to_delete.items():
            Model = pool.get(model)
            Model.delete(records)
