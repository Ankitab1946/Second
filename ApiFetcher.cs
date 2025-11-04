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
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Threading.Tasks;

namespace SSOExample
{
    public class Program
    {
        static async Task Main(string[] args)
        {
            string baseUrl = "https://auth.client.xyz.com";
            string appUrl = "https://app.client.xyz.com/api/v1";

            try
            {
                using (var handler = new HttpClientHandler
                {
                    UseCookies = true,
                    CookieContainer = new CookieContainer(),
                    UseDefaultCredentials = true,   // 🔹 Enables Windows/AD-based SSO
                    AllowAutoRedirect = true
                })
                using (var client = new HttpClient(handler))
                {
                    // Step 1: Request SSO authentication (no username/password)
                    var ssoUrl = $"{baseUrl}/authn/authenticate/sso";
                    Console.WriteLine($"Requesting SSO from: {ssoUrl}");

                    var ssoResponse = await client.GetAsync(ssoUrl);
                    if (!ssoResponse.IsSuccessStatusCode)
                    {
                        Console.WriteLine($"SSO failed: {ssoResponse.StatusCode}");
                        return;
                    }

                    // At this point, the user’s domain credentials (Kerberos/NTLM) are used automatically
                    // The cookie container should now have an SSO session cookie
                    var cookies = handler.CookieContainer.GetCookies(new Uri(baseUrl));
                    foreach (Cookie cookie in cookies)
                    {
                        Console.WriteLine($"Cookie: {cookie.Name} = {cookie.Value}");
                    }

                    // Step 2: Use SSO cookie to call app API
                    client.DefaultRequestHeaders.Accept.Add(new MediaTypeWithQualityHeaderValue("application/json"));
                    var apiResponse = await client.GetAsync($"{appUrl}/user/profile");

                    if (apiResponse.IsSuccessStatusCode)
                    {
                        var result = await apiResponse.Content.ReadAsStringAsync();
                        Console.WriteLine("✅ API Call Successful!");
                        Console.WriteLine(result);
                    }
                    else
                    {
                        Console.WriteLine($"API Call Failed: {apiResponse.StatusCode}");
                        string err = await apiResponse.Content.ReadAsStringAsync();
                        Console.WriteLine($"Error: {err}");
                    }
                }
            }
            catch (Exception ex)
            {
                Console.WriteLine($"❌ Exception: {ex.Message}");
            }
        }
    }
}
