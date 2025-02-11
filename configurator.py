# This file is part of Tryton.  The COPYRIGHT file at the top level of
# this repository contains the full copyright notices and license terms.
from collections import defaultdict
from trytond.model import (ModelSQL, ModelView, fields,
    sequence_ordered, UnionMixin)
from trytond.pool import Pool
from trytond.pyson import Bool, Eval
from sql import Column, Literal
from lxml import etree
from trytond.rpc import RPC
from trytond.transaction import Transaction


class ModelViewMixin:
    __slots__ = ()

    @classmethod
    def fields_view_get(cls, view_id=None, view_type='form', level=None):
        view_id = view_id or None
        ViewConfigurator = Pool().get('view.configurator')
        user = Transaction().user or None

        if ((view_type and view_type != 'tree')
                or Transaction().context.get('avoid_custom_view')
                or cls.__name__ == 'view.configurator'):
            return super().fields_view_get(view_id, view_type, level)

        configurations = ViewConfigurator.search([
            ('model.name', '=', cls.__name__),
            ('view', '=', view_id),
            ('user', 'in', (None, user)),
            ], order=[('user', 'ASC')], limit=1)
        if not configurations:
            return super().fields_view_get(view_id, view_type, level)

        view_configurator, = configurations
        key = (cls.__name__, view_configurator.id)
        cached = cls._fields_view_get_cache.get(key)
        if cached:
            return cached

        result = super().fields_view_get(view_id, view_type, level)
        if result.get('type') != 'tree':
            return result
        xml = view_configurator.generate_xml()
        parser = etree.XMLParser(remove_blank_text=True)
        tree = etree.fromstring(xml, parser)

        if level is None:
            level = 1 if result['type'] == 'tree' else 0

        result['arch'], result['fields'] = cls.parse_view(tree, 'tree',
            field_children=result['field_childs'], level=level)
        cls._fields_view_get_cache.set(key, result)
        return result


class ViewConfiguratorSnapshot(ModelSQL, ModelView):
    'View configurator Snapshot'
    __name__ = 'view.configurator.snapshot'

    view = fields.Many2One('view.configurator', 'View', required=True)
    field = fields.Many2One('ir.model.field', 'Field')
    button = fields.Many2One('ir.model.button', 'Button')


class ViewConfigurator(ModelSQL, ModelView):
    '''View Configurator'''
    __name__ = 'view.configurator'

    model = fields.Many2One('ir.model', 'Model', required=True)
    model_name = fields.Function(fields.Char('Model Name'),
        'on_change_with_model_name')
    user = fields.Many2One('res.user', 'User')
    view = fields.Many2One('ir.ui.view', 'View',
        domain=[
            ('type', 'in', (None, 'tree')),
            ('model', '=', Eval('model_name')),
            ('inherit', '=',  None),
        ])
    snapshot = fields.One2Many('view.configurator.snapshot', 'view', 'Snapshot',
        readonly=True)
    lines = fields.One2Many('view.configurator.line', 'view', "Lines",
        states={
            'readonly': ~Bool(Eval('snapshot', [])),
            })

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._buttons.update({
            'do_snapshot': {},
            })
        cls.__rpc__.update({
            'get_custom_view': RPC(readonly=False, unique=False),
            })

    @classmethod
    def delete(cls, views):
        pool = Pool()
        Snapshot = pool.get('view.configurator.snapshot')
        Lines = pool.get('view.configurator.line')
        snapshots = []
        lines = []
        for view in views:
            snapshots += [x for x in view.snapshot]
            lines += [x for x in view.lines]
        Lines.delete(lines)
        Snapshot.delete(snapshots)
        super().delete(views)

    @classmethod
    def copy(cls, lines, default=None):
        if default is None:
            default = {}
        else:
            default = default.copy()
        default.setdefault('snapshot', None)
        return super().copy(lines, default=default)

    @classmethod
    def get_custom_view(cls, model_name, view_id):
        pool = Pool()
        Model = pool.get('ir.model')
        View = pool.get('ir.ui.view')

        if view_id == 'null':
            view_id = None

        if view_id and view_id != None:
            view_id = int(view_id)

        user = Transaction().user
        domain = [('model.name','=', model_name), ('user', '=', user)]
        if view_id:
            domain += [('view', '=', view_id)]

        custom_views = cls.search(domain, limit=1)
        if custom_views:
            custom_view, = custom_views
            return custom_view.id

        model, = Model.search([('name', '=', model_name)])
        custom_view = cls()
        custom_view.model = model
        if view_id:
            custom_view.view = View(view_id)
        custom_view.user = user
        custom_view.save()
        return custom_view.id

    @fields.depends('model')
    def on_change_with_model_name(self, name=None):
        return self.model and self.model.name or None

    @classmethod
    def create(cls, vlist):
        views = super().create(vlist)
        for view in views:
            view.create_snapshot()
        ModelView._fields_view_get_cache.clear()
        return views

    @classmethod
    def write(cls, views, values, *args):
        super().write(views, values, *args)
        ModelView._fields_view_get_cache.clear()

    def generate_xml(self):
        pool = Pool()

        xml = '<?xml version="1.0"?>\n'
        xml += '<tree>\n'
        new_lines, _ = self.get_difference()

        if self.view:
            ViewTreeOptional = pool.get('ir.ui.view_tree_optional')
            viewtreeoptionals = ViewTreeOptional.search([
                    ('view_id', '=', self.view),
                    ('user', '=', Transaction().user),
                    ])
            optionals = {o.field: o.value for o in viewtreeoptionals}
        else:
            optionals = {}

        for line in self.lines + tuple(new_lines):
            if getattr(line, 'field', None):
                if line.field.name in ('create_uid', 'create_date',
                        'write_uid', 'write_date'):
                    continue

                name = 'name="%s"' % line.field.name

                optional = ''
                if line.optional:
                    if line.field.name in optionals:
                        op = str(int(optionals[line.field.name]))
                    elif line.optional == 'show':
                        op = '0'
                    elif line.optional == 'hide':
                        op = '1'
                    optional = f'optional="{op}"'

                invisible = ''
                if line.searchable:
                    invisible = 'tree_invisible="1"'

                expand = ''
                if line.expand:
                    expand = 'expand="%s"' % line.expand

                sum_ = ''
                if (getattr(line, 'sum_', None) and line.field.ttype in (
                        'integer', 'float', 'numeric', 'timedelta')):
                    sum_ = 'sum="1"'

                attributes = ' '.join([name, optional, invisible, expand, sum_])

                if line.field.ttype == 'datetime':
                    xml+= "<field %s widget='date'/>\n" % attributes
                    xml+= "<field %s widget='time'/>\n" % attributes
                else:
                    xml+= "<field %s/>\n" % attributes
            elif getattr(line, 'button', None):
                name = 'name="%s"' % line.button.name

                invisible = ''
                if line.searchable:
                    invisible = 'tree_invisible="1"'

                attributes = ' '.join([name, invisible])
                xml += "<button %s/>\n" % attributes
        xml += '</tree>'
        return xml

    def get_difference(self):
        pool = Pool()
        Model = pool.get(self.model.name)
        Snapshot = pool.get('view.configurator.snapshot')
        FieldLine = pool.get('view.configurator.line.field')
        ButtonLine = pool.get('view.configurator.line.button')
        Button = pool.get('ir.model.button')
        with Transaction().set_context(avoid_custom_view=True):
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

        sbuttons = Button.search([
            ('model', '=', self.model.name),
            ])
        for button in sbuttons:
            resources[button.name] = button

        def create_lines(type_, resource, expand, optional, invisible):
            if type_ == 'field':
                line = FieldLine()
                line.type = 'ir.model.field'
                line.field = resource
                line.view = self
                line.sequence = 100
            elif type_ == 'button':
                line = ButtonLine()
                line.type = 'ir.model.button'
                line.button = resource
                line.view = self
                line.sequence = 900
            line.searchable = invisible
            line.expand = expand
            line.optional = optional
            return line

        def create_snapshot(type_, resource):
            snapshot = Snapshot()
            snapshot.view = self
            if type_ == 'field':
                snapshot.field = resource
            else:
                snapshot.button = resource
            existing_snapshot.append(resource)
            return snapshot

        lines = []
        snapshots = []
        for child in tree:
            type_ = child.tag
            if type_ not in ('field', 'button'):
                continue
            attributes = child.attrib
            name = attributes['name']
            expand = attributes.get('expand', None)
            if attributes.get('optional', None) == '0':
                optional = 'hide'
            elif attributes.get('optional', None) == '1':
                optional = 'show'
            else:
                optional = None
            invisible = attributes.get('tree_invisible', False)
            if resources.get(name) and resources.get(name) not in existing_snapshot:
                line = create_lines(type_, resources[name], expand, optional,
                    invisible)
                snap = create_snapshot(type_, resources[name])
                lines.append(line)
                snapshots.append(snap)
        return lines, snapshots

    def create_snapshot(self):
        pool = Pool()
        Snapshot = pool.get('view.configurator.snapshot')
        FieldLine = pool.get('view.configurator.line.field')
        ButtonLine = pool.get('view.configurator.line.button')

        (lines, snapshots) = self.get_difference()
        FieldLine.save([x for x in lines if x.type == 'ir.model.field'])
        ButtonLine.save([x for x in lines if x.type == 'ir.model.button'])
        Snapshot.save(snapshots)

    @classmethod
    @ModelView.button
    def do_snapshot(cls, views):
        for view in views:
            view.create_snapshot()


class ViewConfiguratorLineButton(sequence_ordered(), ModelSQL, ModelView):
    '''View Configurator Line Button'''
    __name__ = 'view.configurator.line.button'

    view = fields.Many2One('view.configurator',
        'View Configurator', required=True)
    button = fields.Many2One('ir.model.button', 'Button',
        domain=[
            ('model', '=', Eval('parent_model')),
        ])
    expand = fields.Integer('Expand')
    optional = fields.Selection([
            (None, ''),
            ('show', 'Show'),
            ('hide', 'Hide'),
            ], 'Optional')
    searchable = fields.Boolean('Searchable')
    type = fields.Selection([
        ('ir.model.button', 'Button'),
        ], 'Type')
    parent_model = fields.Function(fields.Char('Model'),
        'on_change_with_parent_model')

    @staticmethod
    def default_type():
        return 'ir.model.button'

    @fields.depends('view', '_parent_view.model')
    def on_change_with_parent_model(self, name=None):
        return self.view.model.name if self.view else None


class ViewConfiguratorLineField(sequence_ordered(), ModelSQL, ModelView):
    '''View Configurator Line Field'''
    __name__ = 'view.configurator.line.field'

    view = fields.Many2One('view.configurator',
        'View Configurator', required=True)
    field = fields.Many2One('ir.model.field', 'Field',
        domain=[
            ('model', '=', Eval('parent_model')),
        ])
    expand = fields.Integer('Expand')
    optional = fields.Selection([
            (None, ''),
            ('show', 'Show'),
            ('hide', 'Hide'),
            ], 'Optional')
    searchable = fields.Boolean('Searchable')
    type = fields.Selection([
        ('ir.model.field', 'Field'),
        ], 'Type')
    parent_model = fields.Function(fields.Char('Model'),
        'on_change_with_parent_model')
    sum_ = fields.Boolean('Sum')

    @staticmethod
    def default_type():
        return 'ir.model.field'

    @fields.depends('view', '_parent_view.model')
    def on_change_with_parent_model(self, name=None):
        return self.view.model.name if self.view else None


class ViewConfiguratorLine(UnionMixin, ModelSQL, ModelView):
    '''View Configurator Line'''
    __name__ = 'view.configurator.line'
    sequence = fields.Integer('Sequence')
    view = fields.Many2One('view.configurator',
        'View Configurator', ondelete='CASCADE', required=True)
    type = fields.Selection([
        ('ir.model.button', 'Button'),
        ('ir.model.field', 'Field'),
        ], 'Type', required=True)
    field = fields.Many2One('ir.model.field', 'Field',
        domain=[
            ('model_ref', '=',
                Eval('_parent_view', Eval('context', {})).get('model', -1))
        ], states={
            'required': Eval('type') == 'ir.model.field',
            'invisible': Eval('type') != 'ir.model.field',
        })
    button = fields.Many2One('ir.model.button', 'Button',
        domain=[
            ('model_ref', '=',
                Eval('_parent_view', Eval('context', {})).get('model', -1))
        ], states={
            'required': Eval('type') == 'ir.model.button',
            'invisible': Eval('type') != 'ir.model.button',
        })
    expand = fields.Integer('Expand',
        states={
        })
    optional = fields.Selection([
            (None, ''),
            ('show', 'Show'),
            ('hide', 'Hide'),
            ], "Optional", help="If left empty, the field is not optional. If "
        "set to 'Show', the field is optional and shown by default. If set "
        "to 'Hide', the field is optional and hidden by default.")
    searchable = fields.Boolean('Searchable')
    sum_ = fields.Boolean('Sum', states={
            'invisible': (Eval('type') != 'ir.model.field')
            })

    @classmethod
    def __setup__(cls):
        super().__setup__()
        cls._order.insert(0, ('sequence', 'ASC NULLS FIRST'))

    @staticmethod
    def default_searchable():
        return False

    @staticmethod
    def default_type():
        return 'ir.model.field'

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
        return super().union_column(name,
            field, table, Model)

    @classmethod
    def create(cls, vlist):
        pool = Pool()

        vlist = [x.copy() for x in vlist]
        models_to_create = defaultdict(list)
        for line in vlist:
            type_ = 'view.configurator.line.field'
            if 'button' in line['type'] :
                type_ = 'view.configurator.line.button'
                if 'field' in line:
                    del line['field']
            else:
                if 'button' in line:
                    del line['button']
            models_to_create[type_].append(line)

        for model, arguments in models_to_create.items():
            Model = pool.get(model)
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
