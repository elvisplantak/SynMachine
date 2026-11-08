using System.Net.Security;
using System.Net.Http.Headers;
using System.Reflection;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;
using Grpc.Core;
using Grpc.Net.Client;
using SiLA2;
using SiLA2.Communication.Services;
using SiLA2.Server.Utils;
using Sila2.Org.Silastandard;
using Sila2.Org.Silastandard.Core.Silaservice.V1;
using SilaString = Sila2.Org.Silastandard.Protobuf.String;
using SilaInteger = Sila2.Org.Silastandard.Protobuf.Integer;

// A separate C# implementation: no Python imports, backend HTTP or state-file access.
return await Run(args);

static async Task<int> Run(string[] args)
{
    var action = args.FirstOrDefault() ?? "help";
    if (action is "help" or "--help")
    {
        Console.WriteLine("SynMachine fake-only SiLA client (.NET / SiLA2.Client.Dynamic 10.3.3)\n" +
            "Actions: discover, status, recipes, read, validate, start, progress, watch, stop\n" +
            "Required: --port N --certificate FILE --server-uuid UUID --token-file FILE\n" +
            "read: --recipe-id ID | validate: --definition FILE\n" +
            "start: --recipe FILE --readiness FILE --run-id ID\n" +
            "progress/watch: --run-id ID | stop: --operation-id ID\n" +
            "watch: optional --watch-seconds N (default 60). Loopback/TLS only. No Start retry.");
        return 0;
    }

    bool startAttempted = false;
    string? runId = null;
    try
    {
        var allowed = new HashSet<string> { "discover", "status", "recipes", "read", "validate",
            "start", "progress", "watch", "stop" };
        if (!allowed.Contains(action) || args.Length % 2 != 1)
            throw new ArgumentException("unknown action or incomplete --name value pair; use help");
        var options = new Dictionary<string, string>();
        var names = new HashSet<string> { "--port", "--certificate", "--server-uuid", "--recipe-id",
            "--definition", "--recipe", "--readiness", "--run-id", "--operation-id", "--watch-seconds", "--token-file" };
        for (int i = 1; i < args.Length; i += 2)
            if (!names.Contains(args[i]) || !options.TryAdd(args[i], args[i + 1]))
                throw new ArgumentException("unknown or duplicate option");
        string Required(string name) => options.TryGetValue(name, out var value) && !string.IsNullOrWhiteSpace(value)
            ? value : throw new ArgumentException($"missing {name}");

        var port = int.Parse(Required("--port"));
        if (port is < 1 or > 65535) throw new ArgumentException("port must be in 1..65535");
        var expectedUuid = Guid.Parse(Required("--server-uuid")).ToString();
        using var pinned = X509CertificateLoader.LoadCertificateFromFile(Required("--certificate"));
        using var handler = new HttpClientHandler { UseProxy = false };
        handler.ServerCertificateCustomValidationCallback = (_, certificate, _, errors) =>
            certificate is not null &&
            (errors & (SslPolicyErrors.RemoteCertificateNameMismatch | SslPolicyErrors.RemoteCertificateNotAvailable)) == 0 &&
            DateTime.UtcNow >= certificate.NotBefore.ToUniversalTime() &&
            DateTime.UtcNow <= certificate.NotAfter.ToUniversalTime() &&
            CryptographicOperations.FixedTimeEquals(certificate.GetCertHash(HashAlgorithmName.SHA256),
                                                    pinned.GetCertHash(HashAlgorithmName.SHA256));
        using var http = new HttpClient(handler) { Timeout = TimeSpan.FromSeconds(10) };
        if (options.TryGetValue("--token-file", out var tokenPath))
        {
            var token = File.ReadAllText(tokenPath).Trim();
            if (!System.Text.RegularExpressions.Regex.IsMatch(token, "\\A[A-Za-z0-9_-]{32,128}\\z"))
                throw new ArgumentException("client token file has an invalid format");
            http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        }
        using var channel = GrpcChannel.ForAddress($"https://127.0.0.1:{port}", new GrpcChannelOptions
        {
            HttpClient = http,
            MaxRetryAttempts = 1,
        });
        var core = new SiLAService.SiLAServiceClient(channel);
        var uuid = await core.Get_ServerUUIDAsync(new Get_ServerUUID_Parameters(), deadline: DateTime.UtcNow.AddSeconds(10));
        if (uuid.ServerUUID.Value != expectedUuid)
            throw new InvalidOperationException("server UUID differs from the explicitly selected fake server");

        var features = new Dictionary<string, Feature>();
        var implemented = await core.Get_ImplementedFeaturesAsync(new Get_ImplementedFeatures_Parameters(),
                                                                 deadline: DateTime.UtcNow.AddSeconds(10));
        foreach (var id in implemented.ImplementedFeatures)
        {
            var fdl = await core.GetFeatureDefinitionAsync(new GetFeatureDefinition_Parameters { FeatureIdentifier = id },
                                                           deadline: DateTime.UtcNow.AddSeconds(10));
            features.Add(id.Value, FeatureGenerator.ReadFeatureFromXml(fdl.FeatureDefinition.Value));
        }
        var messages = new DynamicMessageService(new PayloadFactory(new DynamicAssemblyBuilder()));
        Feature Vendor(string identifier) => features[$"com.github.elvisplantak.synmachine/recipes/{identifier}/v1"];
        string Property(string feature, string name)
            => Value(messages.GetUnobservableProperty(name, channel, Vendor(feature)), name);
        JsonElement Command(string name, Dictionary<string, object> parameters, string feature = "SynMachineExecution")
            => Parse(Value(messages.ExecuteUnobservableCommand(name, channel, Vendor(feature), parameters), "Result"));
        // No multicast discovery, automatic retries or replacement of caller-owned IDs.
        var state = Parse(Property("SynMachineStatus", "Status"));
        if (state.GetProperty("execution").GetProperty("transport_mode").GetString() != "FAKE")
            throw new InvalidOperationException("this client requires an explicitly FAKE server");
        switch (action)
        {
            case "discover":
                Print(new { server_uuid = expectedUuid, features = features.Keys.ToArray() });
                break;
            case "status": Print(state); break;
            case "recipes": Console.WriteLine(Property("SynMachineRecipes", "Recipes")); break;
            case "read":
                Print(Command("ReadRecipe", Strings(("RecipeId", Required("--recipe-id"))), "SynMachineRecipes"));
                break;
            case "validate":
                Print(Command("ValidateRecipe", Strings(("DefinitionJson", File.ReadAllText(Required("--definition")))),
                              "SynMachineRecipes"));
                break;
            case "start":
                runId = Required("--run-id");
                var saved = Parse(File.ReadAllText(Required("--recipe")));
                var readiness = File.ReadAllText(Required("--readiness"));
                if (Parse(readiness).ValueKind != JsonValueKind.Object)
                    throw new ArgumentException("readiness must be an explicit JSON object");
                var parameters = Strings(("RecipeId", saved.GetProperty("recipe_id").GetString()!),
                    ("RunId", runId), ("ExpectedContentDigest", saved.GetProperty("content_digest").GetString()!),
                    ("ReadinessJson", readiness));
                parameters.Add("ExpectedRevision", new SilaInteger { Value = saved.GetProperty("revision").GetInt64() });
                startAttempted = true;
                Print(Command("StartRecipe", parameters));
                break;
            case "progress":
                Print(Command("GetProgress", Strings(("RunId", Required("--run-id")))));
                break;
            case "watch":
                runId = Required("--run-id");
                int seconds = options.TryGetValue("--watch-seconds", out var duration) ? int.Parse(duration) : 60;
                if (seconds is < 1 or > 3600) throw new ArgumentException("watch-seconds must be in 1..3600");
                var deadline = DateTime.UtcNow.AddSeconds(seconds);
                do
                {
                    var progress = Command("GetProgress", Strings(("RunId", runId)));
                    Print(progress);
                    if (progress.GetProperty("status").GetString() is "COMPLETED" or "ABORTED" or "FAULTED")
                        return 0;
                    await Task.Delay(250);
                } while (DateTime.UtcNow < deadline);
                throw new TimeoutException("watch ended; inspect progress using the same run ID");
            case "stop":
                Print(Command("Stop", Strings(("OperationId", Required("--operation-id")))));
                break;
        }
        return 0;
    }
    catch (Exception caught) when (caught is not OutOfMemoryException)
    {
        var error = caught;
        while (error is TargetInvocationException && error.InnerException is not null) error = error.InnerException;
        if (error is RpcException rpc)
        {
            PrintError(new
            {
                error = rpc.StatusCode.ToString(),
                detail = rpc.Status.Detail,
                backend = BackendError(rpc),
                run_id = runId,
                start_attempted = startAttempted
            });
        }
        else PrintError(new
        {
            error = error.GetType().Name,
            detail = error.Message,
            run_id = runId,
            start_attempted = startAttempted
        });
        if (startAttempted)
            Console.Error.WriteLine("Start was attempted. Inspect progress/status using the SAME run ID. No retry was made.");
        return startAttempted ? 3 : 2;
    }
}

static Dictionary<string, object> Strings(params (string Name, string Value)[] pairs)
    => pairs.ToDictionary(x => x.Name, x => (object)new SilaString { Value = x.Value });

static string Value(object response, string field)
{
    var wrapped = response.GetType().GetProperty(field)?.GetValue(response)
        ?? throw new InvalidOperationException($"SiLA response lacks {field}");
    return (string)(wrapped.GetType().GetProperty("Value")?.GetValue(wrapped)
        ?? throw new InvalidOperationException($"SiLA response lacks {field}.Value"));
}

static JsonElement Parse(string json)
{
    using var document = JsonDocument.Parse(json);
    return document.RootElement.Clone();
}

static void Print(object value) => Console.WriteLine(JsonSerializer.Serialize(value));
static void PrintError(object value) => Console.Error.WriteLine(JsonSerializer.Serialize(value));

static JsonElement? BackendError(RpcException error)
{
    if (error.StatusCode != StatusCode.Aborted) return null;
    try
    {
        // Use the independent SDK's standard SiLA error decoder, retaining raw detail as well.
        var message = ErrorHandling.RetrieveSiLAError(error)?.DefinedExecutionError?.Message;
        return message is null ? null : Parse(message);
    }
    catch (Exception malformed) when (malformed is FormatException or JsonException or Google.Protobuf.InvalidProtocolBufferException)
    {
        return null;
    }
}
