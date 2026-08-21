from crewai_agents import Message, Role

# ---------------------------------------------------------------------------
# Scenario 1: Long multi-turn history, ends in a hybrid + multi-intent query
# ---------------------------------------------------------------------------
history_1 = [
    Message(role=Role.USER, content="Hi, I'm looking into TMT bars for a residential project."),
    Message(role=Role.ASSISTANT, content="Sure! SRMB manufactures TMT bars in several grades, including Fe500, Fe500D, and Fe550D."),
    Message(role=Role.USER, content="What's the difference between Fe500D and Fe550D?"),
    Message(role=Role.ASSISTANT, content="Fe550D has higher yield strength and better ductility, making it suitable for seismic zones, while Fe500D is more commonly used in standard residential construction."),
    Message(role=Role.USER, content="Okay, I think I'll go with Fe550D. What sizes are available?"),
    Message(role=Role.ASSISTANT, content="Fe550D is available in 8mm, 10mm, 12mm, 16mm, 20mm, 25mm, and 32mm diameters."),
    Message(role=Role.USER, content="Great, I placed an order last week, invoice number SRMB-2291."),
    Message(role=Role.ASSISTANT, content="Got it, I've noted invoice #SRMB-2291 for your Fe550D order."),
]
current_message_1 = (
    "Can you pull up the yield strength spec sheet for what I ordered, "
    "and also confirm the warranty period and delivery status for invoice #SRMB-2291?"
)

# ---------------------------------------------------------------------------
# Scenario 2: Purely conceptual/open-ended -> should route semantic
# ---------------------------------------------------------------------------
history_2 = [
    Message(role=Role.USER, content="I'm new to construction materials, just trying to learn the basics."),
    Message(role=Role.ASSISTANT, content="No problem, happy to help you get oriented."),
    Message(role=Role.USER, content="What makes TMT bars better than regular mild steel bars?"),
    Message(role=Role.ASSISTANT, content="TMT bars go through a thermo-mechanical treatment that gives them a tough outer layer and a soft ductile core, improving both strength and earthquake resistance compared to plain mild steel."),
]
current_message_2 = (
    "Why does that combination of a hard outer layer and soft core actually "
    "help during earthquakes? I want to understand the underlying mechanism, "
    "not just the marketing pitch."
)

# ---------------------------------------------------------------------------
# Scenario 3: Long history, current message bundles 3 distinct intents
# (tests requires_decomposition + top_k variation)
# ---------------------------------------------------------------------------
history_3 = [
    Message(role=Role.USER, content="We're comparing vendors for our new warehouse project."),
    Message(role=Role.ASSISTANT, content="Understood, I can help compare SRMB against other TMT bar suppliers."),
    Message(role=Role.USER, content="We already shortlisted SRMB and Vyapar Steel."),
    Message(role=Role.ASSISTANT, content="Good choices. Both offer Fe500D and Fe550D grades with similar certifications."),
    Message(role=Role.USER, content="Our last order from SRMB was invoice #SRMB-2291, and from Vyapar it was #VYP-77410."),
    Message(role=Role.ASSISTANT, content="Noted both invoice numbers for reference."),
    Message(role=Role.USER, content="We also had a delayed shipment issue with SRMB back in March."),
    Message(role=Role.ASSISTANT, content="I see — I'll keep that shipment delay context in mind."),
]
current_message_3 = (
    "Give me the warranty terms for invoice #SRMB-2291 and #VYP-77410, "
    "a general explanation of why thermo-mechanical treatment improves "
    "corrosion resistance, and also check if SRMB has had any other "
    "delayed shipment complaints besides the one in March."
)

# ---------------------------------------------------------------------------
# Scenario 4: Short/no meaningful history, but current message is hybrid-heavy
# (tests behavior with minimal context)
# ---------------------------------------------------------------------------
history_4 = [
    Message(role=Role.USER, content="Hello"),
    Message(role=Role.ASSISTANT, content="Hi! How can I help you today?"),
]
current_message_4 = (
    "Show me the technical datasheet for SKU SRMB-FE550D-16MM, batch number "
    "B24-0817, and confirm if it passed IS 1786:2008 certification."
)

# ---------------------------------------------------------------------------
# Scenario 5: Coreference-heavy semantic follow-up (tests pronoun resolution)
# ---------------------------------------------------------------------------
history_5 = [
    Message(role=Role.USER, content="What's the environmental impact of steel manufacturing?"),
    Message(role=Role.ASSISTANT, content="Steel manufacturing is energy-intensive and a major source of industrial CO2 emissions, primarily from blast furnace operations."),
    Message(role=Role.USER, content="Does SRMB do anything about that?"),
    Message(role=Role.ASSISTANT, content="Yes, SRMB has invested in induction furnace technology and uses scrap-based production to reduce emissions compared to traditional blast furnaces."),
]
current_message_5 = (
    "How does that compare to what other Indian manufacturers are doing, "
    "and is it actually making a measurable difference?"
)