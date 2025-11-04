// using System;
// using System.Collections.Generic;
// using System.Net.Http;
// using System.Net.Http.Headers;
// using System.Threading.Tasks;
// using System.Windows.Forms;
// using Newtonsoft.Json.Linq;
// using Excel = Microsoft.Office.Interop.Excel;

// namespace ExcelFinanceAddIn
// {
//     public static class ApiFetcher
//     {
//         private static readonly string baseUrl = "https://auth.client.xyz.com";
//         private static readonly string appUrl = "http://localhost:8000/api/v1";
//         private static readonly string userName = "sdsjdfh@intranet.xyz.com";
//         private static readonly string password = Environment.GetEnvironmentVariable("Password") ?? "";

//         public static async Task FetchDataAsync()
//         {
//             try
//             {
//                 using (HttpClientHandler handler = new HttpClientHandler())
//                 {
//                     handler.ServerCertificateCustomValidationCallback = (msg, cert, chain, errors) => true;
//                     using (HttpClient client = new HttpClient(handler))
//                     {
//                         // Step 1: Get Token
//                         var authnUrl = $"{baseUrl}/authn/authentication/sso/api";
//                         var authParams = new[]
//                         {
//                             "appname=Testprojectct",
//                             "redirecturl=http://none"
//                         };
//                         var authUrl = $"{authnUrl}?{string.Join("&", authParams)}";

//                         var byteArray = System.Text.Encoding.ASCII.GetBytes($"{userName}:{password}");
//                         client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Basic", Convert.ToBase64String(byteArray));

//                         var tokenResponse = await client.GetAsync(authUrl);
//                         tokenResponse.EnsureSuccessStatusCode();

//                         var tokenJson = await tokenResponse.Content.ReadAsStringAsync();
//                         var tokenObj = JObject.Parse(tokenJson);
//                         string appToken = tokenObj["apptoken"]?.ToString();

//                         if (string.IsNullOrEmpty(appToken))
//                             throw new Exception("App token not found in response.");

//                         // Step 2: Get session cookie
//                         var formData = new FormUrlEncodedContent(new[]
//                         {
//                             new KeyValuePair<string, string>("appToken", appToken)
//                         });

//                         var authResponse = await client.PostAsync($"{appUrl}/user", formData);
//                         authResponse.EnsureSuccessStatusCode();

//                         // Step 3: Call report API
//                         var reportEndpoint = $"{appUrl}/user";
//                         using (var reportClient = new HttpClient(handler))
//                         {
//                             reportClient.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/octet-stream"));
//                             reportClient.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", appToken);

//                             var reportResponse = await reportClient.GetAsync(reportEndpoint);
//                             reportResponse.EnsureSuccessStatusCode();

//                             var reportData = await reportResponse.Content.ReadAsStringAsync();

//                             // ✅ Write response to Excel
//                             Excel.Application app = Globals.ThisAddIn.Application;
//                             Excel.Worksheet ws = app.ActiveSheet;
//                             ws.Cells[1, 1].Value = "API Response:";
//                             ws.Cells[2, 1].Value = reportData;

//                             MessageBox.Show("App validation successfully completed!", "Success", MessageBoxButtons.OK, MessageBoxIcon.Information);
//                         }
//                     }
//                 }
//             }
//             catch (Exception ex)
//             {
//                 MessageBox.Show($"Error: {ex.Message}", "API Fetch Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
//             }
//         }
//     }
// }

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows.Forms;
using Newtonsoft.Json.Linq;

namespace YourVSTOAddIn
{
    public static class ApiFetcher
    {
        private static readonly string baseUrl = "https://auth.client.xyz.com";
        private static readonly string appUrl = "http://localhost:8000/api/v1";
        private static readonly string userName = "sdsjdfh@intranet.xyz.com";
        private static readonly string password = Environment.GetEnvironmentVariable("Password") ?? "";

        public static async Task<string> FetchDataAsync()
        {
            try
            {
                using (var handler = new HttpClientHandler())
                {
                    handler.ServerCertificateCustomValidationCallback = (msg, cert, chain, errors) => true;
                    handler.AllowAutoRedirect = true;

                    using (var client = new HttpClient(handler))
                    {
                        //
                        // STEP 1 – Authenticate & Get Token
                        //
                        var authnUrl = $"{baseUrl}/authn/authenticate/sso";
                        var authUrl = $"{authnUrl}?appname=Testprojectct&redirecturl=http://none";

                        var byteArray = Encoding.ASCII.GetBytes($"{userName}:{password}");
                        client.DefaultRequestHeaders.Authorization =
                            new AuthenticationHeaderValue("Basic", Convert.ToBase64String(byteArray));

                        MessageBox.Show($"Calling: {authUrl}", "Debug - Step 1");

                        var tokenResponse = await client.GetAsync(authUrl);
                        var tokenHtml = await tokenResponse.Content.ReadAsStringAsync();

                        if (!tokenResponse.IsSuccessStatusCode)
                            throw new Exception($"Auth failed: {tokenResponse.StatusCode}\n\n{tokenHtml}");

                        //
                        // Try to parse the token out of HTML form
                        //
                        var tokenMatch = Regex.Match(tokenHtml, @"name\s*=\s*[""']?Token[""']?\s*value\s*=\s*[""']?(?<token>[^""'>\s]+)");
                        var appToken = tokenMatch.Success ? tokenMatch.Groups["token"].Value : null;

                        if (string.IsNullOrEmpty(appToken))
                        {
                            MessageBox.Show(tokenHtml, "HTML Response");
                            throw new Exception("❌ Token not found in HTML response.");
                        }

                        MessageBox.Show($"✅ Token Found: {appToken}", "Debug - Token Extracted");

                        //
                        // STEP 2 – Exchange token for session / cookie
                        //
                        var jsonData = new JObject { ["appToken"] = appToken }.ToString();
                        var content = new StringContent(jsonData, Encoding.UTF8, "application/json");

                        var sessionUrl = $"{appUrl}/user";
                        MessageBox.Show($"Posting token to: {sessionUrl}", "Debug - Step 2");

                        var authResponse = await client.PostAsync(sessionUrl, content);
                        var body = await authResponse.Content.ReadAsStringAsync();

                        MessageBox.Show($"Status: {authResponse.StatusCode}\n\nResponse:\n{body}", "Debug - Step 2 Result");

                        if (!authResponse.IsSuccessStatusCode)
                            throw new Exception($"Step 2 failed: {authResponse.StatusCode}\nBody: {body}");

                        //
                        // STEP 3 – Return success or cookie data
                        //
                        return appToken;
                    }
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error: {ex.Message}", "API Fetch Error", MessageBoxButtons.OK, MessageBoxIcon.Error);
                return null;
            }
        }
    }
}
