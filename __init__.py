import bpy
import nodeitems_utils

import json, hashlib

class CustomNodetreeNodeBase:
    inputs_def  = {}
    nodes_def   = {}
    outputs_def = {}

    _node_def_hash = None
    current_hash: bpy.props.StringProperty(options={"HIDDEN"})

    @staticmethod
    def setup_inputs(node_tree, inputs_def):
        node_tree.inputs.clear()

        for name, (input_type, attrs) in inputs_def.items():
            node_tree.inputs.new(input_type, name)
            if not isinstance(attrs, dict):
                raise TypeError(f"{attrs} has type '{type(attrs).__name__}', expected 'dict'")
            for attribute, value in attrs.items():
                setattr(node_tree.inputs[name], attribute, value)

        node_input = node_tree.nodes.new("NodeGroupInput")
        node_input.name = "inputs"

    @staticmethod
    def setup_nodes(node_tree, nodes_def, label_nodes=True):
        nodes = node_tree.nodes
        links = node_tree.links

        if not isinstance(nodes_def, dict):
            raise TypeError(f"nodes_def has type '{type(nodes_def).__name__}', expected 'dict'")
        for name, (node_type, attrs, inputs) in nodes_def.items():
            node = nodes.new(node_type)
            node.name = name

            if label_nodes:
                node.label = " ".join((word.capitalize() for word in name.split("_")))

            if not isinstance(attrs, dict):
                raise TypeError(f"{attrs} has type '{type(attrs).__name__}', expected 'dict'")
            for attr, value in attrs.items():
                setattr(node, attr, value)

            if not isinstance(inputs, dict):
                raise TypeError(f"{inputs} has type '{type(inputs).__name__}', expected 'dict'")
            for input_index, value in inputs.items():
                if not isinstance(value, tuple):
                    node.inputs[input_index].default_value = value
                    continue

                try:
                    from_node, output_index = value
                except ValueError as e:
                    raise ValueError(f"invalid link '{value}', expected '(node, index)'") from e
                try:
                    socket_output = nodes[from_node].outputs[output_index]
                except KeyError as e:
                    raise KeyError(f"'{from_node}' has no '{output_index}' output") from e
                try:
                    socket_input = node.inputs[input_index]
                except KeyError as e:
                    raise KeyError(f"'{node.name}' has no '{input_index}' input") from e

                links.new(socket_output, socket_input)

    @staticmethod
    def setup_outputs(node_tree, outputs_def):
        node_tree.outputs.clear()

        nodes = node_tree.nodes
        links = node_tree.links

        for name, (output_type, attrs, _) in outputs_def.items():
            node_tree.outputs.new(output_type, name)
            if not isinstance(attrs, dict):
                raise TypeError(f"{attrs} has type '{type(attrs).__name__}', expected 'dict'")
            for attribute, attribute_value in attrs.items():
                setattr(node_tree.outputs[name], attribute, attribute_value)

        node_output = nodes.new("NodeGroupOutput")
        node_output.name = "outputs"

        for name, (_, _, value) in outputs_def.items():
            if not isinstance(value, tuple):
                node_output.inputs[name].default_value = value
            else:
                from_node, output_index = value
                links.new(nodes[from_node].outputs[output_index], node_output.inputs[name])

    def init(self, context):
        cls = self.__class__

        self.current_hash = self.get_node_def_hash()

        if not (node_tree := self.node_tree):
            node_tree_name = f"CUSTOM_NODE_{cls.__name__}"
            node_tree = bpy.data.node_groups.new(node_tree_name, "ShaderNodeTree")

        node_tree.nodes.clear()
        CustomNodetreeNodeBase.setup_inputs(node_tree, cls.inputs_def)
        CustomNodetreeNodeBase.setup_nodes(node_tree, cls.nodes_def)
        CustomNodetreeNodeBase.setup_outputs(node_tree, cls.outputs_def)
        self.node_tree = node_tree
        self.update_custom_node()

    def update_custom_node(self):
        self.update()
        # self.socket_value_update(bpy.context)

    def _upgrade_custom_node(self):
        if self.current_hash == self.get_node_def_hash():
            return
        print(f"{COLOR_INFO}[custom_node_utils] updating '{self.node_tree.name}'{COLOR_END}")
        CustomNodetreeNodeBase.init(self, bpy.context)

    def copy(self, node):
        self.node_tree = node.node_tree.copy()
        self.current_hash = node.current_hash
        self.update_custom_node()

    def free(self):
        if self.node_tree.users < 1:
            bpy.data.node_groups.remove(self.node_tree)

    def draw_buttons(self, context, layout):
        for prop in self.bl_rna.properties:
            if prop.is_runtime and not (prop.is_readonly or prop.is_hidden):
                text = "" if prop.type == "ENUM" else prop.name
                layout.prop(self, prop.identifier, text=text)

    @classmethod
    def get_node_def_hash(cls):
        if cls._node_def_hash is None:
            hash_content = (cls.inputs_def, cls.nodes_def, cls.outputs_def)
            node_def_json = json.dumps(hash_content, default=str)
            cls._node_def_hash = hashlib.sha1(node_def_json.encode()).hexdigest()
        return cls._node_def_hash

class SharedCustomNodetreeNodeBase(CustomNodetreeNodeBase):
    def init(self, context):
        name = f"CUSTOM_NODE_{self.__class__.__name__}"
        if not self.node_tree and (node_tree := bpy.data.node_groups.get(name)):
            self.node_tree = node_tree
            self.current_hash = self.get_node_def_hash()
            self.update_custom_node()
        else:
            super().init(context)

    def copy(self, node):
        self.node_tree = node.node_tree
        self.current_hash = node.current_hash
        self.update_custom_node()

@bpy.app.handlers.persistent
def upgrade_custom_nodes(context):
    for node_tree in (mat.node_tree for mat in bpy.data.materials if mat.use_nodes):
        for node in node_tree.nodes:
            if isinstance(node, CustomNodetreeNodeBase):
                node._upgrade_custom_node()

def register_node_category(identifier, category):
    def draw_node_item(self, context):
        layout = self.layout
        col = layout.column(align=True)
        for item in self.category.items(context):
            item.draw(item, col, context)

    menu_type = type("NODE_MT_category_" + category.identifier, (bpy.types.Menu,), {
        "bl_space_type": "NODE_EDITOR",
        "bl_label": category.name,
        "category": category,
        "poll": category.poll,
        "draw": draw_node_item,
    })

    bpy.utils.register_class(menu_type)

    nodeitems_utils._node_categories[identifier][0].append(category)
    nodeitems_utils._node_categories[identifier][2].append(menu_type)

    bpy.app.handlers.load_post.append(upgrade_custom_nodes)

def unregister_node_category(identifier, category):
    categories = nodeitems_utils._node_categories[identifier][0]
    menu_types = nodeitems_utils._node_categories[identifier][2]

    menu_type = menu_types[categories.index(category)]
    bpy.utils.unregister_class(menu_type)

    categories.remove(category)
    menu_types.remove(menu_type)

    bpy.app.handlers.load_post.remove(upgrade_custom_nodes)

COLOR_INFO = "\033[96m"
COLOR_END = "\033[0m"
