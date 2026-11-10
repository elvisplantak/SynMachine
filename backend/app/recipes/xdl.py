"""Bounded XDL 2 linear interchange, never a second recipe executor.

Independent implementation of the public format (reference SDK tag 2.1.0).
Only liquid Add, Transfer and passive Wait are representable by this profile.
All device decisions, validation, persistence and execution stay in Recipes.
"""

from decimal import Decimal, localcontext
import re
import xml.etree.ElementTree as ET
from typing import Literal

from defusedxml.ElementTree import DefusedXMLParser
from defusedxml.common import DefusedXmlException
from pydantic import BaseModel, ConfigDict, Field

from app.recipes.models import RecipeDefinition, recipe_content_digest, validate_recipe_flow

PROFILE = "synmachine-xdl2-linear-v1"
MAX_XML_BYTES = 131072
ROLES = {"REACTOR": {"reactor", "ChemputerReactor"},
         "SF": {"separator", "ChemputerSeparator"}, "COLUMN": {"column"}}
EXPORT_TYPES = {"REACTOR": "reactor", "SF": "separator", "COLUMN": "column"}
VOLUME_UNITS = {"mL": Decimal(1), "ml": Decimal(1), "L": Decimal(1000),
                "l": Decimal(1000), "uL": Decimal("0.001"), "µL": Decimal("0.001"),
                "μL": Decimal("0.001")}
TIME_UNITS = {"s": Decimal(1), "sec": Decimal(1), "seconds": Decimal(1),
              "min": Decimal(60), "mins": Decimal(60), "h": Decimal(3600)}


class XdlError(ValueError):
    pass


class XdlRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)
    xml: str = Field(min_length=1, max_length=MAX_XML_BYTES)


class XdlImportRequest(XdlRequest):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    # Physical bottle -> declared reagent name; logical role -> declared component ID.
    reagents: dict[Literal["B1", "B2", "S"], str] = Field(max_length=3)
    vessels: dict[Literal["REACTOR", "SF", "COLUMN"], str] = Field(max_length=3)


class XdlExportRequest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    definition: RecipeDefinition


class _BoundedTree(ET.TreeBuilder):
    def __init__(self):
        super().__init__()
        self.depth = self.nodes = 0
        self.version = None

    def start(self, tag, attrs):
        self.depth += 1
        self.nodes += 1
        if self.depth > 8 or self.nodes > 512:
            raise XdlError("XDL exceeds the document depth or element limit")
        return super().start(tag, attrs)

    def end(self, tag):
        result = super().end(tag)
        self.depth -= 1
        return result

    def pi(self, target, text):
        if (target != "xdl" or self.version is not None or self.nodes != 0
            or re.fullmatch(r'''version\s*=\s*(?:"2\.0\.0"|'2\.0\.0')\s*''', text) is None):
            raise XdlError("Only the XDL 2.0.0 format declaration is supported")
        self.version = "2.0.0"


def _attrs(node, allowed, required=()):
    if set(node.attrib) - set(allowed) or set(required) - set(node.attrib):
        raise XdlError(f"XDL {node.tag}: unsupported or missing attributes")


def _leaf(node):
    if len(node):
        raise XdlError(f"XDL {node.tag}: nested content is unsupported")


def _identifier(value):
    if (not value.strip() or len(value) > 120 or any(c in value for c in "${}")):
        raise XdlError("XDL identifiers must be nonblank, at most 120 characters and literal")
    return value


def _false_flags(node, names):
    if any(node.get(name, "false").lower() != "false" for name in names):
        raise XdlError(f"XDL {node.tag}: requested stirring, special handling or solids are unsupported")


def _amount(value, units):
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*([A-Za-zµμ]+)\s*", value)
    if match is None or match[2] not in units or len(match[1]) > 40:
        raise XdlError("XDL quantities require a positive decimal and a supported explicit unit")
    # No binary float, rounding, expressions, molar/mass conversion or implicit units.
    with localcontext() as context:
        context.prec = 64
        result = Decimal(match[1]) * units[match[2]]
    if not 0 < result <= Decimal("1000000"):
        raise XdlError("XDL quantity is outside the interchange range (0, 1000000]")
    return format(result, "f")


def _read(xml):
    try:
        size = len(xml.encode("utf-8"))
    except UnicodeError:
        raise XdlError("XDL requires valid UTF-8 text") from None
    if size > MAX_XML_BYTES:
        raise XdlError("XDL exceeds the 128 KiB UTF-8 limit")
    builder = _BoundedTree()
    parser = DefusedXMLParser(target=builder, forbid_dtd=True,
                             forbid_entities=True, forbid_external=True)
    try:
        parser.feed(xml)
        root = parser.close()
    except (ET.ParseError, DefusedXmlException, UnicodeError):
        raise XdlError("XDL must be well-formed XML without DTDs, entities or external resources") from None
    for node in root.iter():
        if (node.text and node.text.strip()) or (node.tail and node.tail.strip()):
            raise XdlError("XDL text content is unsupported; use declared attributes")
    if root.tag == "XDL":
        _attrs(root, ())
        if len(root) != 1 or root[0].tag != "Synthesis":
            raise XdlError("XDL requires exactly one Synthesis; blueprints are unsupported")
        synthesis = root[0]
    elif root.tag == "Synthesis" and builder.version == "2.0.0":
        synthesis = root
    else:
        raise XdlError("Use an XDL 2 wrapper or an explicit XDL 2.0.0 declaration")
    _attrs(synthesis, {"id"})
    if "id" in synthesis.attrib:
        _identifier(synthesis.attrib["id"])
    sections = {}
    for section in synthesis:
        if section.tag not in {"Metadata", "Hardware", "Reagents", "Procedure"} or section.tag in sections:
            raise XdlError("XDL requires unique supported sections; parameters/variables are unsupported")
        sections[section.tag] = section
    if not {"Hardware", "Reagents", "Procedure"} <= sections.keys():
        raise XdlError("XDL requires Hardware, Reagents and Procedure")
    description = ""
    if "Metadata" in sections:
        metadata = sections["Metadata"]
        _attrs(metadata, {"description"})
        _leaf(metadata)
        description = metadata.get("description", "")
        if len(description) > 2000:
            raise XdlError("XDL description exceeds 2000 characters")
    for name in ("Hardware", "Reagents", "Procedure"):
        _attrs(sections[name], ())
    components = {}
    for node in sections["Hardware"]:
        if node.tag != "Component":
            raise XdlError("XDL Hardware supports Component declarations only")
        _attrs(node, {"id", "type"}, {"id", "type"})
        _leaf(node)
        identity = _identifier(node.attrib["id"])
        if identity in components:
            raise XdlError("XDL component IDs must be unique")
        components[identity] = node.attrib["type"]
    reagents = []
    for node in sections["Reagents"]:
        if node.tag != "Reagent":
            raise XdlError("XDL Reagents supports Reagent declarations only")
        _attrs(node, {"name", "solid", "stir"}, {"name"})
        _leaf(node)
        _false_flags(node, ("solid", "stir"))
        identity = _identifier(node.attrib["name"])
        if identity in reagents:
            raise XdlError("XDL reagent names must be unique")
        reagents.append(identity)
    steps = list(sections["Procedure"])
    if not 1 <= len(steps) <= 100:
        raise XdlError("XDL requires 1..100 linear steps")
    for index, node in enumerate(steps, 1):
        _leaf(node)
        if node.tag == "Add":
            _attrs(node, {"vessel", "reagent", "volume", "stir", "dropwise", "viscous"},
                   {"vessel", "reagent", "volume"})
            _false_flags(node, ("stir", "dropwise", "viscous"))
            if node.get("reagent") not in reagents:
                raise XdlError(f"XDL step {index}: reagent is not declared")
            if node.get("vessel") not in components:
                raise XdlError(f"XDL step {index}: vessel is not declared")
            _amount(node.attrib["volume"], VOLUME_UNITS)
        elif node.tag == "Transfer":
            _attrs(node, {"from_vessel", "to_vessel", "volume", "solid", "viscous"},
                   {"from_vessel", "to_vessel", "volume"})
            _false_flags(node, ("solid", "viscous"))
            if any(node.get(key) not in components for key in ("from_vessel", "to_vessel")):
                raise XdlError(f"XDL step {index}: transfer vessel is not declared")
            _amount(node.attrib["volume"], VOLUME_UNITS)
        elif node.tag == "Wait":
            _attrs(node, {"time"}, {"time"})
            _amount(node.attrib["time"], TIME_UNITS)
        else:
            raise XdlError(f"XDL step {index}: operation {node.tag} is unsupported")
    return synthesis, description, components, reagents, steps


def inspect_xdl(xml):
    synthesis, _, components, reagents, steps = _read(xml)
    return {"profile": PROFILE, "format_version": "2.0.0", "reference_release": "2.1.0",
            "suggested_name": synthesis.get("id", "Imported XDL")[:120],
            "reagents": reagents, "vessels": [
                {"id": key, "type": value} for key, value in components.items()],
            "step_count": len(steps)}


def import_xdl(request: XdlImportRequest):
    synthesis, description, components, reagents, steps = _read(request.xml)
    for mapping, declared in ((request.reagents, reagents), (request.vessels, components)):
        if len(set(mapping.values())) != len(mapping) or any(value not in declared for value in mapping.values()):
            raise XdlError("XDL bindings must be unique references to declared names/IDs")
    for role, identity in request.vessels.items():
        if components[identity] not in ROLES[role]:
            raise XdlError(f"XDL {role} binding has an unsupported component type")
    bottles = {identity: role for role, identity in request.reagents.items()}
    vessels = {identity: role for role, identity in request.vessels.items()}
    translated = []
    for index, node in enumerate(steps, 1):
        if node.tag == "Add":
            if node.get("vessel") not in vessels or vessels[node.get("vessel")] != "REACTOR":
                raise XdlError(f"XDL step {index}: Add must target the explicitly bound REACTOR")
            if node.get("reagent") not in bottles:
                raise XdlError(f"XDL step {index}: assign the reagent to B1, B2 or S")
            translated.append({"kind": "ADD", "source": bottles[node.get("reagent")],
                               "volume_ml": _amount(node.attrib["volume"], VOLUME_UNITS)})
        elif node.tag == "Transfer":
            route = (vessels.get(node.get("from_vessel")), vessels.get(node.get("to_vessel")))
            if route not in {("REACTOR", "SF"), ("SF", "COLUMN")}:
                raise XdlError(f"XDL step {index}: bind a supported REACTOR→SF or SF→COLUMN route")
            translated.append({"kind": "TRANSFER", "route": "_TO_".join(route),
                               "volume_ml": _amount(node.attrib["volume"], VOLUME_UNITS)})
        else:
            translated.append({"kind": "WAIT", "duration_seconds": _amount(node.attrib["time"], TIME_UNITS)})
    definition = RecipeDefinition(name=request.name if request.name is not None else synthesis.get("id", "Imported XDL"),
                                  description=description, sources={**{"B1": "B1", "B2": "B2", "S": "S"},
                                  **request.reagents}, steps=translated)
    validate_recipe_flow(definition)
    return definition


def export_xdl(definition: RecipeDefinition):
    for index, step in enumerate(definition.steps, 1):
        if step.kind not in {"ADD", "TRANSFER", "WAIT"}:
            raise XdlError(f"XDL export step {index}: {step.kind} has no supported exact XDL mapping")
        value = step.duration_seconds if step.kind == "WAIT" else step.volume_ml
        if (not 0 < value <= Decimal("1000000") or len(value.as_tuple().digits) > 50
            or abs(value.as_tuple().exponent) > 50):
            raise XdlError("XDL export quantity exceeds the interchange range or precision limit")
    validate_recipe_flow(definition)
    labels = definition.sources.model_dump()
    for label in labels.values():
        _identifier(label)
    if len(set(labels.values())) != 3:
        raise XdlError("XDL export requires distinct bottle labels to preserve reagent identity")
    _identifier(definition.name)
    root = ET.Element("XDL")
    synthesis = ET.SubElement(root, "Synthesis", id=definition.name)
    ET.SubElement(synthesis, "Metadata", description=definition.description)
    hardware = ET.SubElement(synthesis, "Hardware")
    for role, component_type in EXPORT_TYPES.items():
        ET.SubElement(hardware, "Component", id=role, type=component_type)
    declarations = ET.SubElement(synthesis, "Reagents")
    for label in labels.values():
        ET.SubElement(declarations, "Reagent", name=label)
    procedure = ET.SubElement(synthesis, "Procedure")
    for index, step in enumerate(definition.steps, 1):
        if step.kind == "ADD":
            ET.SubElement(procedure, "Add", reagent=labels[step.source], vessel="REACTOR",
                          volume=f"{format(step.volume_ml, 'f')} mL", stir="false")
        elif step.kind == "TRANSFER":
            source, target = step.route.split("_TO_")
            ET.SubElement(procedure, "Transfer", from_vessel=source, to_vessel=target,
                          volume=f"{format(step.volume_ml, 'f')} mL")
        elif step.kind == "WAIT":
            ET.SubElement(procedure, "Wait", time=f"{format(step.duration_seconds, 'f')} s")
        else:
            raise XdlError(f"XDL export step {index}: {step.kind} has no supported exact XDL mapping")
    ET.indent(root)
    xml = '<?xdl version="2.0.0"?>\n' + ET.tostring(root, encoding="unicode") + "\n"
    # Apply the exact same bounded profile to output, including numeric limits.
    _read(xml)
    return {"profile": PROFILE, "xml": xml, "content_digest": recipe_content_digest(definition),
            "reagents": labels, "vessels": {role: role for role in ROLES}}
