
module RainbowComponents
using Dash

const resources_path = realpath(joinpath( @__DIR__, "..", "deps"))
const version = "0.0.1"

include("jl/filepicker.jl")
include("jl/rainbowcomponents.jl")

function __init__()
    DashBase.register_package(
        DashBase.ResourcePkg(
            "rainbow_components",
            resources_path,
            version = version,
            [
                DashBase.Resource(
    relative_package_path = "async-RainbowComponents.js",
    external_url = "https://unpkg.com/rainbow_components@0.0.1/rainbow_components/async-RainbowComponents.js",
    dynamic = nothing,
    async = :true,
    type = :js
),
DashBase.Resource(
    relative_package_path = "async-RainbowComponents.js.map",
    external_url = "https://unpkg.com/rainbow_components@0.0.1/rainbow_components/async-RainbowComponents.js.map",
    dynamic = true,
    async = nothing,
    type = :js
),
DashBase.Resource(
    relative_package_path = "rainbow_components.min.js",
    external_url = nothing,
    dynamic = nothing,
    async = nothing,
    type = :js
),
DashBase.Resource(
    relative_package_path = "rainbow_components.min.js.map",
    external_url = nothing,
    dynamic = true,
    async = nothing,
    type = :js
)
            ]
        )

    )
end
end
