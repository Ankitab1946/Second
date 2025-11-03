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
using System.Net.Http;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace YourVSTOAddIn
{
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
                    handler.ServerCertificateCustomValidationCallback = (msg, cert, chain, errors) => true;
                    using (HttpClient client = new HttpClient(handler))
                    {
                        var loginUrl = $"{baseUrl}/authn/authenticate/sso";
                        var authParams = $"appname=Testprojectct&redirecturl=http://none";
                        var byteArray = System.Text.Encoding.ASCII.GetBytes($"{userName}:{password}");
                        client.DefaultRequestHeaders.Authorization = new System.Net.Http.Headers.AuthenticationHeaderValue("Basic", Convert.ToBase64String(byteArray));

                        var tokenResponse = await client.GetAsync($"{loginUrl}?{authParams}");
                        var htmlContent = await tokenResponse.Content.ReadAsStringAsync();

                        if (!tokenResponse.IsSuccessStatusCode)
                        {
                            MessageBox.Show($"Login failed: {tokenResponse.StatusCode}", "Auth Error");
                            return;
                        }

                        // 🧩 Extract token from HTML form
                        string token = ExtractTokenFromHtml(htmlContent);

                        if (string.IsNullOrEmpty(token))
                        {
                            MessageBox.Show("Token not found in HTML response.", "Parse Error");
                            return;
                        }

                        MessageBox.Show($"✅ Extracted Token:\n{token}", "Success");

                        // Use token for next call
                        await UseTokenAsync(client, token);
                    }
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show($"Error: {ex.Message}", "API Fetch Error");
            }
        }

        private static string ExtractTokenFromHtml(string html)
        {
            // Use Regex to find the token value inside <input type="hidden" name="Token" value="...">
            var match = Regex.Match(html, @"name\s*=\s*[""']Token[""']\s*value\s*=\s*[""']([^""']+)[""']", RegexOptions.IgnoreCase);
            return match.Success ? match.Groups[1].Value : null;
        }

        private static async Task UseTokenAsync(HttpClient client, string token)
        {
            var formData = new FormUrlEncodedContent(new[]
            {
                new KeyValuePair<string, string>("appToken", token)
            });

            var response = await client.PostAsync($"{appUrl}/user", formData);
            string result = await response.Content.ReadAsStringAsync();

            MessageBox.Show($"Response using Token:\n{result.Substring(0, Math.Min(result.Length, 300))}", "Step 2 Success");
        }
    }
}
