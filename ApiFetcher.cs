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

using System.Net.Http;
using System.Net.Http.Headers;
using Newtonsoft.Json.Linq;
using System;
using System.Windows.Forms;

public class ApiFetcher
{
    private static readonly string baseUrl = "https://auth.client.xyz.com";
    private static readonly string appUrl = "http://localhost:8000/api/v1";
    private static readonly string userName = "sdsjdfh@intranet.xyz.com";
    private static readonly string password = Environment.GetEnvironmentVariable("Password") ?? "";

    public static async Task FetchDataAsync()
    {
        try
        {
            using (HttpClientHandler handler = new HttpClientHandler())
            {
                handler.AllowAutoRedirect = true;
                handler.ServerCertificateCustomValidationCallback = (msg, cert, chain, err) => true;

                using (HttpClient client = new HttpClient(handler))
                {
                    client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
                    client.DefaultRequestHeaders.Add("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64)");

                    // 🧩 STEP 1: Send login as form POST
                    var loginUrl = $"{baseUrl}/authn/authenticate/sso";
                    var loginData = new FormUrlEncodedContent(new[]
                    {
                        new KeyValuePair<string, string>("username", userName),
                        new KeyValuePair<string, string>("password", password),
                        new KeyValuePair<string, string>("appname", "Testprojectct"),
                        new KeyValuePair<string, string>("redirecturl", "http://none")
                    });

                    var loginResponse = await client.PostAsync(loginUrl, loginData);
                    string loginContent = await loginResponse.Content.ReadAsStringAsync();

                    if (!loginResponse.IsSuccessStatusCode)
                    {
                        MessageBox.Show($"Error during login:\nStatus: {loginResponse.StatusCode}\n{loginContent}", "Login Failed");
                        return;
                    }

                    if (loginContent.TrimStart().StartsWith("<"))
                    {
                        MessageBox.Show("Received HTML (login form) — this endpoint requires SSO browser login.", "HTML Response");
                        return;
                    }

                    // ✅ Parse token
                    var tokenObj = JObject.Parse(loginContent);
                    string appToken = tokenObj["apptoken"]?.ToString();

                    if (string.IsNullOrEmpty(appToken))
                    {
                        MessageBox.Show("App token not found in response.", "Missing Token");
                        return;
                    }

                    MessageBox.Show($"✅ Authenticated successfully!\nToken: {appToken.Substring(0, Math.Min(appToken.Length, 20))}...", "Success");

                    // 🧩 STEP 2: Example of next call
                    client.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", appToken);
                    var response = await client.GetAsync($"{appUrl}/user");
                    response.EnsureSuccessStatusCode();
                    var json = await response.Content.ReadAsStringAsync();

                    MessageBox.Show($"API3 Response:\n{json.Substring(0, Math.Min(500, json.Length))}");
                }
            }
        }
        catch (Exception ex)
        {
            MessageBox.Show($"Error: {ex.Message}", "API Error");
        }
    }
}
